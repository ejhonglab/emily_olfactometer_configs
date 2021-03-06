"""
Takes YAML input describing a panels of odors and returns config to present
them, either in the order in the YAML or randomly. Odors are assigned to random
valves from the set of available valves (identified by the pin number driving
them).

No mixtures (across odor vials) supported in this config generation function.

Only planning on supporting the case where the number of odors in the panel can
fit into the number of valves available in the particular hardware.

Example input (the part between the ```'s, saved to a YAML file, whose filename
is passed as input to `make_config_dict` below):
```
# Since I have not yet implemented some orthogonal way of specifying the setup,
# and the corresponding wiring / available pins / etc on each.
available_valve_pins: [2, 3, 4]

balance_pin: 5

# If this is False, the odors will be presented in the order in the list below.
randomize_presentation_order: False

odors:
 - name: 2,3-butanedione
   log10_conc: -6
 - name: methyl salicylate
   log10_conc: -3

# Reformatted into settings.timing.*_us by [this] generator
pre_pulse_s: 2
pulse_s: 1
post_pulse_s: 11
```
"""

import random
import warnings

from olfactometer.generators import common


def make_config_dict(generator_config_yaml_dict):
    """
    Args:
    generator_config_yaml_dict (str): dict of parsed contents of YAML
      configuration file.

    Returns `dict` representation of YAML config for olfactometer. Also includes
    a `pins2odors` YAML dictionary which is not used by the olfactometer, but
    which is for tracking which odors certain pins corresponded to, at analysis
    time.

    Used keys in the YAML that gets parsed and input to this function (as a
    dict):
    - Used via `common.parse_common_settings`:
      - 'pre_pulse_s'
      - 'pulse_s'
      - 'post_pulse_s'
      - 'timing_output_pin' (optional)
        - Should be specified in separate hardware config.

      - 'recording_indicator_pin' (optional)
        - Should be specified in separate hardware config.

    - Used via `common.get_available_pins`:
      - Either:
        - All of the keys in `common.single_manifold_specific_keys`, OR...
        - All of the keys in `common.two_manifold_specific_keys`

        In both cases above, those parameters should be specified in separate
        hardware config.

    - Used directly in this function:
      - 'odors'
      - 'randomize_presentation_order' (optional, defaults to True)
      - 'n_repeats' (optional, defaults to 1)

    """
    data = generator_config_yaml_dict

    generated_config_dict = common.parse_common_settings(data)

    available_valve_pins, pins2balances, single_manifold = \
        common.get_available_pins(data, generated_config_dict)

    odors = data['odors']
    # Each element of odors, which is a dict, must at least have a `name`
    # describing what that odor is (e.g. the chemical name).
    assert all([('name' in o) for o in odors])
    assert type(odors) is list

    n_odors = len(odors)
    assert len(available_valve_pins) >= n_odors
    # The means of generating the random odor vial <-> pin (valve) mapping.
    odor_pins = random.sample(available_valve_pins, n_odors)

    # The YAML dump downstream (which SHOULD include this data) should sort the
    # keys by default (just for display purposes, but still what I want).
    pins2odors = {p: o for p, o in zip(odor_pins, odors)}

    randomize_presentation_order_key = 'randomize_presentation_order'
    if randomize_presentation_order_key in data:
        randomize_presentation_order = data[randomize_presentation_order_key]
        assert randomize_presentation_order in (True, False)
    else:
        if len(odors) > 1:
            warnings.warn(f'defaulting to {randomize_presentation_order_key}'
                '=True, since not specified in config'
            )
            randomize_presentation_order = True
        else:
            assert len(odors) == 1
            randomize_presentation_order = False

    n_repeats_key = 'n_repeats'
    if n_repeats_key in data:
        n_repeats = data[n_repeats_key]
        if randomize_presentation_order:
            warnings.warn('current implementation only randomizes across odors,'
                ' keeping presentations of any given odor together'
            )
    else:
        n_repeats = 1

    trial_pins = odor_pins
    if randomize_presentation_order:
        # This re-orders odor_pins in-place (it modifies it, rather than
        # returning something modified).
        random.shuffle(trial_pins)

    trial_pinlists = [[p] for p in trial_pins for _ in range(n_repeats)]

    pinlist_at_each_trial = common.add_balance_pins(
        trial_pinlists, pins2balances
    )

    co2_odors = [o for o in odors if o['name'] == 'CO2']
    if len(co2_odors) > 0:
        assert 'co2_pin' in data

        if len(co2_odors) > 1:
            # Since we only have one 'co2_pin'
            raise NotImplementedError

        co2_odor = co2_odors[0]

        curr_co2_pins = [p for p, o in pins2odors.items() if o['name'] == 'CO2']
        assert len(curr_co2_pins) == 1
        curr_co2_pin = curr_co2_pins[0]

        pins2odors[curr_co2_pin] = {
            'name': 'air for co2-mixture compensation',
            'log10_conc': 0,
        }
        co2_pin = data['co2_pin']
        pins2odors[co2_pin] = co2_odor

        assert not any([co2_pin in pl for pl in pinlist_at_each_trial])
        pinlist_at_each_trial = [pl + [co2_pin] if curr_co2_pin in pl else pl
            for pl in pinlist_at_each_trial
        ]

    generated_config_dict['pins2odors'] = pins2odors
    common.add_pinlist(pinlist_at_each_trial, generated_config_dict)

    return generated_config_dict

