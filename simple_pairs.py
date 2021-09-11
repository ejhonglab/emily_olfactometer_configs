"""
```
n_repeats: 3

odor_pairs:
 - pair:
   - ethyl hexanoate
   - 1-hexanol
 - pair:
   - limonene
   - linalool

# Reformatted into settings.timing.*_us by [this] generator
pre_pulse_s: 2
pulse_s: 1
post_pulse_s: 11
```
"""
import random
from copy import deepcopy
import warnings

from olfactometer.generators import common

def make_config_dict(data):
    common_generated_config_dict = common.parse_common_settings(data)

    # Currently only supporting the case where the trials are all consecutive.
    n_repeats = data['n_repeats']

    odor_pairs = data['odor_pairs']

    # TODO maybe also support including multiple pairs in one recording,
    # if we have enough available pins (on each manifold)

    # TODO TODO better error message if config seems to be expecting separate
    # hardware config, but it's not set up correctly (and thus one of the
    # asserts about having some of the required keys fails in here)
    available_valve_pins, pins2balances, single_manifold = \
        common.get_available_pins(data, common_generated_config_dict)

    assert not single_manifold

    # don't want to worry about cases with more manifolds for now
    assert len(set(pins2balances.values())) == 2

    # TODO could maybe refactor stuff below to operate directly on outputs
    # and depend less on single_manifold to branch...
    # now i'm just re-extracting these from the config data, just as
    # get_available_pins is doing
    available_group1_valve_pins = data['available_group1_valve_pins']
    available_group2_valve_pins = data['available_group2_valve_pins']
    group1_balance_pin = data['group1_balance_pin']
    group2_balance_pin = data['group2_balance_pin']

    def get_odor_name(odor):
        """
        odor (dict): representation of odor
        """
        return odor['name']

    def get_odor_concs(odor):
        """
        odor (dict): representation of odor
        """
        return odor['log10_concentrations']

    generated_config_dicts = []
    for pair in odor_pairs:
        generated_config_dict = deepcopy(common_generated_config_dict)

        odor1, odor2 = pair['pair']

        odor1_name = get_odor_name(odor1)
        odor2_name = get_odor_name(odor2)

        odor1_log10_concs = get_odor_concs(odor1)
        odor2_log10_concs = get_odor_concs(odor2)

        assert odor1_name != odor2_name
        odor_name2log10_concs = {
            odor1_name: odor1_log10_concs,
            odor2_name: odor2_log10_concs,
        }

        manifold_odors = [odor1_name, odor2_name]

        odor_vials = []
        odor_pins = []
        for n, available_group_valve_pins in zip(manifold_odors,
            (available_group1_valve_pins, available_group2_valve_pins)):

            if n == 'CO2':
                continue

            n_concentrations = len(odor_name2log10_concs[n])
            assert len(available_group_valve_pins) >= n_concentrations + 1

            group_vials = [{'name': n, 'log10_conc': c}
                for c in tuple(odor_name2log10_concs[n])
            ]
            odor_vials.extend(group_vials)

            #odor_pins.extend(random.sample(available_group_valve_pins,
            #    len(group_vials)
            #))
            odor_pins.extend(available_group_valve_pins[:len(group_vials)])

        assert len(odor_vials) == len(odor_pins)

        pins2odors = {p: o for p, o in zip(odor_pins, odor_vials)}

        if 'CO2' in manifold_odors:

            co2_concs = odor_name2log10_concs['CO2']
            assert len(co2_concs) == 1
            co2_conc = co2_concs[0]

            pins2odors[data['co2_pin']] = {'name': 'CO2', 'log10_conc': co2_conc}

            # TODO make work in case where we have other odors connected here too
            co2_air_compensation_pin = available_group_valve_pins[-1]
            pins2odors[co2_air_compensation_pin] = {
                'name': 'air for co2 compensation', 'log10_conc': 0
            }

        # TODO modify so only the keys used below (in get_vial) are included, or
        # modify get_vial so the match works despite any extra keys (just
        # converting all .items() to tuple will make the matches sensitive to
        # this extra information)
        # Just for use within this generator.
        vials2pins = {tuple(o.items()): p for p, o in pins2odors.items()}
        def get_vial_tuple(name, log10_conc=None):
            if single_manifold and log10_conc is None:
                vial_dict = {'name': 'solvent'}
            else:
                assert (type(log10_conc) is int or type(log10_conc) is float
                    or (not single_manifold and log10_conc is None)
                )
                vial_dict = {'name': name, 'log10_conc': log10_conc}
            return tuple(vial_dict.items())

        odor_name_order = (odor1_name, odor2_name)
        # To avoid confusion with n1 and n2 below
        # (i.e. n1 != odor1_name, at least not always).
        del odor1_name, odor2_name

        # The order in `odor_name_order`, and thus which odor name is assigned
        # to `n1` and which to `n2` determines the order in which they ramp.
        # `n1` ramps first (though which is ramped alternates between each set
        # of concentrations).
        n1, n2 = odor_name_order

        def conc_sort_key(conc):
            """Enables concentration sorting that works w/ None
            """
            if conc is not None:
                return conc
            else:
                return float('-inf')

        # TODO choose diff variable names for either these / odor<n>_log10_concs / both,
        # to be more clear on how they actually differ
        odor1_concentrations = tuple(sorted(odor_name2log10_concs[n1],
            key=conc_sort_key
        ))
        odor2_concentrations = tuple(sorted(odor_name2log10_concs[n2],
            key=conc_sort_key
        ))
        pinlist_at_each_trial = []

        # Doing this rather than two (nested) for-loops, because we want to do
        # all combinations of the lower concentrations before moving on to any
        # of the higher concentrations (of either odor).
        for c1 in odor1_concentrations:
            for c2 in odor2_concentrations:

                o1 = get_vial_tuple(n1, c1)
                o2 = get_vial_tuple(n2, c2)

                # This technically would still fail if (somehow) the order of the
                # dictionary items is different in get_vial_tuple than it was when
                # constructing vials2pins above. Probably won't happen though.
                p1 = vials2pins[o1]
                p2 = vials2pins[o2]

                # TODO maybe also use common.add_balance_pins here?

                # Converting to a set first because if p1 == p2 (should only be
                # relevant in the (0,0) case when all odors are on the same
                # manifold, and thus there is only one shared solvent vial), we just
                # want to open that single valve, with all of the flow going through
                # it.
                pins = sorted({p1, p2})
                if not single_manifold:
                    assert len(pins) == 2, ('there should be distinct solvent '
                        'vials in the two manifold case'
                    )
                    # Because there is always going to be one valve opening on each
                    # of the two manifolds, and we will need to close the normally
                    # open valve on each of those manifolds along with that.
                    # Handled differently than "balance_pin" in the single manifold
                    # case because the firmware specifically supports the case where
                    # there is a single balance pin, but it doesn't support two.
                    pins.extend([group1_balance_pin, group2_balance_pin])

                if 'CO2' in (n1, n2):
                    pins.append(co2_air_compensation_pin)

                pinlist_at_each_trial.extend([pins] * n_repeats)

        generated_config_dict['pins2odors'] = pins2odors
        common.add_pinlist(pinlist_at_each_trial, generated_config_dict)

        generated_config_dicts.append(generated_config_dict)

    return generated_config_dicts

