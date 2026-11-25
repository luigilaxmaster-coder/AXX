"""Act appearance: the per-Act renderer studio is validated with AXX's own ranges and reactions keep their states."""
import unittest

from backend.agents.profiles import AgentProfileValidationError, validate_agent_profile
from backend.tests.test_acts_inference import act_spec


def with_appearance(**appearance):
    spec = act_spec('act-look', 'Look', 'Helix', 'axx-connect', 'gpt-6.1-terra')
    spec['appearance'].update(appearance)
    return spec


class ActAppearanceTests(unittest.TestCase):
    def test_studio_is_kept_rounded_and_optional(self):
        clean = validate_agent_profile(with_appearance(studio={'exposure': 1.234567, 'roughness': 0.2, 'light_angle': -90,
                                                                'fluidity': None, 'unknown': 5}))['appearance']
        self.assertEqual(clean['studio'], {'exposure': 1.235, 'roughness': 0.2, 'light_angle': -90.0})
        self.assertNotIn('studio', validate_agent_profile(with_appearance())['appearance'])
        self.assertNotIn('studio', validate_agent_profile(with_appearance(studio={}))['appearance'])

    def test_out_of_range_or_non_numeric_studio_is_rejected(self):
        for bad in ({'exposure': 9}, {'roughness': 0}, {'light_angle': 181}, {'fluidity': float('nan')}, {'exposure': '1.0'},
                    {'exposure': True}, []):
            with self.subTest(bad=bad), self.assertRaises(AgentProfileValidationError):
                validate_agent_profile(with_appearance(studio=bad))

    def test_reactions_keep_known_states_only(self):
        clean = validate_agent_profile(with_appearance(reactions={'working': 'orbit', 'thinking': 'ripple', 'hacked': 'x'}))
        self.assertEqual(clean['appearance']['reactions'], {'working': 'orbit', 'thinking': 'ripple'})


if __name__ == '__main__':
    unittest.main()
