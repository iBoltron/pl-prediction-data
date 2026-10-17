"""Read-only Big Balls EPL data collector; Python 3.11+, standard library only."""
import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

BASE = 'https://api.bigballsdata.com'
LONDON = ZoneInfo('Europe/London')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, key, cap=100):
        if not key:
            raise ValueError('Set BBS_API_KEY in GitHub Actions secrets or your environment.')
        self.key, self.cap, self.calls = key, cap, 0
        self.opener = build_opener(NoRedirect())

    def get(self, path, **params):
        if self.calls >= self.cap:
            raise ValueError('Request budget reached; collection is incomplete.')
        self.calls += 1
        url = BASE + path + ('?' + urlencode(params) if params else '')
        req = Request(url, headers={'Authorization': 'Bearer ' + self.key})
        try:
            with self.opener.open(req, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise ValueError(f'API HTTP {exc.code}; check access/quota. No automatic retry.') from None
        except (URLError, TimeoutError, json.JSONDecodeError):
            raise ValueError('API network or JSON error.') from None
        if not isinstance(payload, dict) or payload.get('error'):
            raise ValueError('Unexpected API envelope or API error.')
        return payload

    def matches(self, **filters):
        rows, pages, seen = [], [], set()
        for offset in range(0, 2000, 200):
            page = self.get('/v1/matches', sport='football', league='epl',
                            limit=200, offset=offset, **filters)
            batch = page.get('data')
            if not isinstance(batch, list):
                raise ValueError('Expected data array; refusing unknown schema.')
            for row in batch:
                if not isinstance(row, dict) or not row.get('id'):
                    raise ValueError('Missing match ID.')
                if row['id'] in seen:
                    raise ValueError('Duplicate match/repeated page; pagination not reliable.')
                seen.add(row['id'])
            rows.extend(batch)
            pages.append(page.get('meta', {}))
            if len(batch) < 200:
                return rows, pages
        raise ValueError('Pagination limit reached; collection incomplete.')


def kickoff(row):
    value = datetime.fromisoformat(row['kickoff_utc'].replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Kickoff lacks time zone.')
    return value


def validate(rows):
    for row in rows:
        if row.get('sport') != 'football' or str(row.get('league', '')).lower() not in {
            'epl', 'premier league', 'english premier league', 'england premier league'
        }:
            raise ValueError('Unexpected competition; inspect provider league naming.')
        kickoff(row)
        for side in ('home', 'away'):
            if not isinstance(row.get(side), dict) or not row[side].get('id'):
                raise ValueError('Missing team identity.')


def xg_available(payload):
    data = payload.get('data') or {}
    if payload.get('meta', {}).get('available') is False:
        return False
    for side in ('home', 'away'):
        value = (data.get(side) or {}).get('expected_goals')
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value < 100:
            return False
    return True


def collect(client, target):
    fixtures, fixture_meta = client.matches(date=target.isoformat(), tz='Europe/London')
    validate(fixtures)
    if any(kickoff(r).astimezone(LONDON).date() != target for r in fixtures):
        raise ValueError('Date filter returned fixtures outside the requested London date.')
    if not fixtures:
        raise ValueError('No fixtures returned: no-games day or missing coverage; verify independently.')
    season = target.year if target.month >= 7 else target.year - 1
    history, history_meta = client.matches(season=season)
    validate(history)
    # Explicitly validate the season window because list rows may omit season.
    if any(not date(season, 7, 1) <= kickoff(r).date() < date(season+1, 7, 1) for r in history):
        raise ValueError('Season filter returned out-of-season rows.')
    now = datetime.now(timezone.utc)
    cutoff = min(now, datetime.combine(target, datetime.min.time(), LONDON))
    history = [r for r in history if r.get('status') == 'finished' and kickoff(r) < cutoff]
    teams = {r[s]['id'] for r in fixtures for s in ('home', 'away')}
    selected, counts = {}, {}
    for team in sorted(teams):
        recent = sorted((r for r in history if team in (r['home']['id'], r['away']['id'])),
                        key=kickoff, reverse=True)[:15]
        counts[team] = len(recent)
        selected.update({r['id']: r for r in recent})
    stats = {}
    for mid in selected:
        stats[mid] = client.get('/v1/matches/' + quote(str(mid), safe='') + '/statistics')
    lineups = {}
    for row in fixtures:
        mid = row['id']
        lineups[mid] = client.get('/v1/stored/matches/' + quote(str(mid), safe='') + '/lineups')
    return {
        'requested_date': str(target), 'retrieved_at': now.isoformat(),
        'source_freshness': 'unknown unless supplied in provider metadata; retrieval time is not source update time',
        'prediction_status': 'not_generated: data collection only; model requires validation',
        'fixture_meta': fixture_meta, 'history_meta': history_meta,
        'fixtures': fixtures, 'recent_matches': list(selected.values()),
        'statistics': stats, 'lineups': lineups,
        'quality': {'history_matches_per_team': counts,
                    'matches_with_numeric_xg_both_sides': sum(xg_available(p) for p in stats.values()),
                    'matches_requested_for_xg': len(stats),
                    'lineups_require_manual_confirmation': True},
        'requests_used': client.calls,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=datetime.now(LONDON).date().isoformat())
    parser.add_argument('--max-requests', type=int, default=100)
    args = parser.parse_args()
    out = Path('output')
    out.mkdir(exist_ok=True)
    # Never leave an older successful run masquerading as this run.
    for name in ('data.json', 'status.json'):
        (out / name).unlink(missing_ok=True)
    try:
        result = collect(Client(os.environ.get('BBS_API_KEY'), args.max_requests), date.fromisoformat(args.date))
        # Defence in depth against accidental provider echo of credentials.
        text = json.dumps(result, indent=2, allow_nan=False)
        text = text.replace(os.environ['BBS_API_KEY'], '[REDACTED]')
        (out / 'data.json').write_text(text)
        print('Saved output/data.json. Review quality and source freshness before modelling.')
    except (ValueError, KeyError, TypeError) as exc:
        message = str(exc).replace(os.environ.get('BBS_API_KEY') or '\0', '[REDACTED]')
        (out / 'status.json').write_text(json.dumps({'status': 'failed', 'reason': message}))
        raise SystemExit(message)


if __name__ == '__main__':
    main()
