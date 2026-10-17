import unittest
from unittest.mock import Mock
from datetime import date
from collect import Client, collect, validate, xg_available


def fixture(**changes):
    row = dict(id='match1', sport='football', league='Premier League',
               kickoff_utc='2026-10-17T14:00:00Z', status='scheduled',
               home={'id': 'a'}, away={'id': 'b'})
    return dict(row, **changes)


class DataTests(unittest.TestCase):
    def test_missing_key(self):
        with self.assertRaises(ValueError): Client('')

    def test_wrong_competition(self):
        with self.assertRaises(ValueError): validate([fixture(league='La Liga')])

    def test_empty_xg_is_not_zero(self):
        self.assertFalse(xg_available({'data': {'home': {}, 'away': {}}}))
        self.assertTrue(xg_available({'data': {'home': {'expected_goals': 0},
                                             'away': {'expected_goals': 1.2}}}))

    def test_unavailable_overrides_values(self):
        self.assertFalse(xg_available({'meta': {'available': False}, 'data': {
            'home': {'expected_goals': 1}, 'away': {'expected_goals': 1}}}))

    def test_repeated_pagination(self):
        c = Client('test')
        c.get = Mock(return_value={'data': [fixture(id=str(i)) for i in range(200)]})
        with self.assertRaisesRegex(ValueError, 'Duplicate'): c.matches()

    def test_wrong_date(self):
        c = Mock()
        c.matches.return_value = ([fixture()], [])
        with self.assertRaisesRegex(ValueError, 'Date filter'): collect(c, date(2026, 10, 18))

    def test_no_fixtures(self):
        c = Mock()
        c.matches.return_value = ([], [])
        with self.assertRaisesRegex(ValueError, 'No fixtures'): collect(c, date(2026, 10, 17))

    def test_finished_history_requested(self):
        c = Mock()
        old = fixture(id='old', kickoff_utc='2026-10-10T14:00:00Z', status='finished')
        c.matches.side_effect = [([fixture()], []), ([old], [])]
        c.get.return_value = {'data': {}, 'meta': {}}
        c.calls = 4
        result = collect(c, date(2026, 10, 17))
        self.assertEqual(c.matches.call_args.kwargs, {'season': 2026, 'status': 'finished'})
        self.assertEqual(result['quality']['history_matches_per_team'], {'a': 1, 'b': 1})
        self.assertEqual(result['quality']['matches_requested_for_xg'], 1)

    def test_empty_history_rejected(self):
        c = Mock()
        c.matches.side_effect = [([fixture()], []), ([], [])]
        with self.assertRaisesRegex(ValueError, 'No completed'):
            collect(c, date(2026, 10, 17))

    def test_upcoming_history_rejected(self):
        c = Mock()
        c.matches.side_effect = [([fixture()], []), ([fixture()], [])]
        with self.assertRaisesRegex(ValueError, 'No completed'):
            collect(c, date(2026, 10, 17))

    def test_budget(self):
        with self.assertRaisesRegex(ValueError, 'budget'): Client('test', 0).get('/v1/user/me')


if __name__ == '__main__':
    unittest.main()
