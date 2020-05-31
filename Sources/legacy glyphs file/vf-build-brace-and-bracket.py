import collections
import io
import itertools
import logging
import os
import sys
from pathlib import Path
from pprint import pprint
from typing import Dict, List, Tuple

import defcon
import fontTools.designspaceLib
import fontTools.ttLib
import fontTools.varLib

# ufo2ft layer compiler branch: https://github.com/googlei18n/ufo2ft/pull/295
import ufo2ft

logger = logging.Logger(__name__)


def generate_variable_font(
    designspace: fontTools.designspaceLib.DesignSpaceDocument
) -> fontTools.ttLib.TTFont:
    load_sources(designspace)
    apply_bracket_layers(designspace)
    apply_brace_layers(designspace)

    master_sources, master_layers = [], []
    for source in designspace.sources:
        master_sources.append(source.font)
        master_layers.append(source.layerName or "public.default")
    masters = list(
        # XXX: fix contour not reversing when inplace==True.
        # XXX: .notdef may have reverse direction in sparse layer: remove?
        ufo2ft.compileInterpolatableTTFs(
            master_sources,
            layerNames=master_layers,
            useProductionNames=False,
            inplace=False,
        )
    )

    try:
        variable_font = merge_masters(designspace, masters)
    except AssertionError:  # Write out masters for inspection.
        for i, m in enumerate(masters):
            m.save(f"{i}.ttf")
        raise

    return variable_font


def load_sources(designspace: fontTools.designspaceLib.DesignSpaceDocument) -> None:
    filename_to_ufo: Dict[os.PathLike, defcon.Font] = {}
    for source in designspace.sources:
        # Only load sources once.
        if source.filename not in filename_to_ufo:
            source_path = Path(designspace.path).parent / source.filename
            source.font = defcon.Font(source_path)
            filename_to_ufo[source.filename] = source.font
        else:
            source.font = filename_to_ufo[source.filename]


def apply_bracket_layers(
    designspace: fontTools.designspaceLib.DesignSpaceDocument
) -> None:
    if designspace.rules:
        logger.info("Substitution rules already present, not adding additional ones.")
        return

    # As of Glyphs.app 2.5.1, only single axis bracket layers are supported.
    bracket_axis = designspace.axes[0]
    # Determine the top of the axis in design space (axis.default may be user space).
    bracket_axis_max = int(
        max([source.location[bracket_axis.name] for source in designspace.sources])
    )

    # Collect bracket layers
    bracket_layers: Dict[int, List[defcon.Layer]] = collections.defaultdict(list)
    for source in designspace.sources:
        for layer in source.font.layers:
            if (
                "[" in layer.name
                and "]" in layer.name
                and ".background" not in layer.name
            ):
                n = layer.name.replace(" ", "")
                try:
                    bracket_minimum = int(n[n.index("[") + 1 : n.index("]")])
                except ValueError as e:
                    raise ValueError(
                        "Only bracket layers with one numerical location (meaning the first axis in the designspace file) are currently supported."
                    ) from e
                assert (
                    bracket_axis.minimum <= bracket_minimum <= bracket_axis.maximum
                ), f"Bracket layer {layer.name} must be within the bounds of the {bracket_axis.name} axis: minimum {bracket_axis.minimum}, maximum {bracket_axis.maximum}."
                bracket_layers[bracket_minimum].append(layer)

    # Enforce that all bracket layers have the same glyphs, i.e. a bracket
    # layer must be made for each master.
    crossovers: Dict[str, List[int]] = collections.defaultdict(list)
    for location, layers in bracket_layers.items():
        glyph_name_set = set(g.name for g in layers[0])
        for layer_other in layers[1:]:
            glyph_name_set_other = set(g.name for g in layer_other)
            assert (
                glyph_name_set == glyph_name_set_other
            ), f"Bracket layer with crossover at {location}: bracket layers for {glyph_name_set ^ glyph_name_set_other} seem to be missing somewhere."
        for glyph_name in glyph_name_set:
            crossovers[glyph_name].append(location)

    # Copy bracket layers to their own glyphs.
    # crossover_subs: Dict[int, List[Tuple[str, str]]] = collections.defaultdict(list)
    for location, layers in bracket_layers.items():
        for layer in layers:
            for bracket_glyph in layer:
                glyph = defcon.Glyph()
                glyph.name = f"{bracket_glyph.name}.BRACKET.{location}"
                glyph.copyDataFromGlyph(bracket_glyph)
                bracket_glyph.font.insertGlyph(glyph)
                # crossover_subs[location].append((bracket_glyph.name, glyph.name))

    # Generate rules for the bracket layers.
    for glyph_name, axis_crossovers in crossovers.items():
        for crossover_min, crossover_max in pairwise(
            axis_crossovers + [bracket_axis_max]
        ):
            rule = fontTools.designspaceLib.RuleDescriptor()
            rule.name = f"{glyph_name}.BRACKET.{crossover_min}"
            rule.conditionSets.append(
                [
                    {
                        "name": bracket_axis.name,
                        "minimum": crossover_min,
                        "maximum": crossover_max,
                    }
                ]
            )
            rule.subs.append((glyph_name, rule.name))
            designspace.addRule(rule)
    # breakpoint()
    #designspace.write("test.ds")


def apply_brace_layers(
    designspace: fontTools.designspaceLib.DesignSpaceDocument
) -> None:
    if any(
        source.layerName not in (None, "public.default")
        for source in designspace.sources
    ):
        logger.info("Sparse layers already present, not adding additional ones.")
        return

    sparse_layers = []
    for source in designspace.sources:
        for layer in source.font.layers:
            if (
                "{" in layer.name
                and "}" in layer.name
                and ".background" not in layer.name
            ):
                n = layer.name
                layer_coordinates = [
                    int(c) for c in n[n.index("{") + 1 : n.index("}")].split(",")
                ]
                assert len(layer_coordinates) == len(designspace.axes)
                layer_coordinates_mapping = {}
                for axis, location in zip(designspace.axes, layer_coordinates):
                    assert (
                        axis.minimum <= location <= axis.maximum
                    ), f"Location {location} is out of bounds for axis {axis.name}"
                    layer_coordinates_mapping[axis.name] = location
                s = fontTools.designspaceLib.SourceDescriptor()
                s.filename = source.filename
                s.layerName = layer.name
                s.font = source.font
                s.location = layer_coordinates_mapping
                sparse_layers.append(s)
    designspace.sources.extend(sparse_layers)


def master_source(
    designspace: fontTools.designspaceLib.DesignSpaceDocument
) -> fontTools.designspaceLib.SourceDescriptor:
    return next(s for s in designspace.sources if s.copyInfo)


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def copy_font_object(font: fontTools.ttLib.TTFont) -> fontTools.ttLib.TTFont:
    buffer = io.BytesIO()
    font.save(buffer)
    buffer.seek(0)
    return fontTools.ttLib.TTFont(buffer)


def merge_masters(
    designspace: fontTools.designspaceLib.DesignSpaceDocument,
    masters: List[fontTools.ttLib.TTFont],
) -> fontTools.ttLib.TTFont:
    assert all("glyf" in f for f in masters)  # Var TTFs only for now.
    designspace_data = load_designspace(designspace)
    assert designspace.sources[designspace_data.base_idx].layerName in (
        None,
        "public.default",
    ), "Default master must not be a sparse master, check the default values for all axes and the corresponding source."

    # Write out to memory and reload all fonts as there are modifications done when
    # saving, messing with OTL merging.
    # XXX: fix?
    masters = [copy_font_object(m) for m in masters]
    variable_font = copy_font_object(masters[designspace_data.base_idx])

    ### COPY-PASTE OF fontTools.varLib.build from 3.33.0
    fvar = fontTools.varLib._add_fvar(
        variable_font, designspace_data.axes, designspace_data.instances
    )
    fontTools.varLib._add_stat(variable_font, designspace_data.axes)
    fontTools.varLib._add_avar(variable_font, designspace_data.axes)

    # Map from axis names to axis tags...
    normalized_master_locs = [
        {designspace_data.axes[k].tag: v for k, v in loc.items()}
        for loc in designspace_data.normalized_master_locs
    ]
    # From here on, we use fvar axes only
    axis_tags = [axis.axisTag for axis in fvar.axes]

    # Assume single-model for now.
    model = fontTools.varLib.models.VariationModel(
        normalized_master_locs, axisOrder=axis_tags
    )
    assert model.mapping[designspace_data.base_idx] == 0

    fontTools.varLib._add_MVAR(variable_font, model, masters, axis_tags)
    fontTools.varLib._add_HVAR(variable_font, model, masters, axis_tags)
    fontTools.varLib._merge_OTL(variable_font, model, masters, axis_tags)
    fontTools.varLib._add_gvar(variable_font, model, masters, optimize=True)
    fontTools.varLib._merge_TTHinting(variable_font, model, masters)
    if designspace_data.rules:
        fontTools.varLib._add_GSUB_feature_variations(
            variable_font,
            designspace_data.axes,
            designspace_data.internal_axis_supports,
            designspace_data.rules,
        )
    ### COPY-PASTE OF fontTools.varLib.build

    return variable_font


def load_designspace(designspace: fontTools.designspaceLib.DesignSpaceDocument):
    # Cribbed from fontTools 3.33.0 and changed to accept a designspace object.
    masters = designspace.sources
    if not masters:
        raise fontTools.varLib.VarLibError("no sources found in .designspace")
    instances = designspace.instances

    standard_axis_map = collections.OrderedDict(
        [
            ("weight", ("wght", {"en": "Weight"})),
            ("width", ("wdth", {"en": "Width"})),
            ("slant", ("slnt", {"en": "Slant"})),
            ("optical", ("opsz", {"en": "Optical Size"})),
        ]
    )

    # Setup axes
    axes: Dict[str, fontTools.designspaceLib.AxisDescriptor] = collections.OrderedDict()
    for axis in designspace.axes:
        axis_name = axis.name
        if not axis_name:
            assert axis.tag is not None
            axis_name = axis.name = axis.tag

        if axis_name in standard_axis_map:
            if axis.tag is None:
                axis.tag = standard_axis_map[axis_name][0]
            if not axis.labelNames:
                axis.labelNames.update(standard_axis_map[axis_name][1])
        else:
            assert axis.tag is not None
            if not axis.labelNames:
                axis.labelNames["en"] = axis_name

        axes[axis_name] = axis

    # Check all master and instance locations are valid and fill in defaults
    for obj in masters + instances:
        obj_name = obj.name or obj.styleName or ""
        loc = obj.location
        for axis_name in loc.keys():
            assert axis_name in axes, "Location axis '%s' unknown for '%s'." % (
                axis_name,
                obj_name,
            )
        for axis_name, axis in axes.items():
            if axis_name not in loc:
                loc[axis_name] = axis.default
            else:
                v = axis.map_backward(loc[axis_name])
                assert axis.minimum <= v <= axis.maximum, (
                    "Location for axis '%s' (mapped to %s) out of range for '%s' [%s..%s]"
                    % (axis_name, v, obj_name, axis.minimum, axis.maximum)
                )

                # Normalize master locations

    internal_master_locs = [o.location for o in masters]

    # TODO This mapping should ideally be moved closer to logic in _add_fvar/avar
    internal_axis_supports = {}
    for axis in axes.values():
        triple = (axis.minimum, axis.default, axis.maximum)
        internal_axis_supports[axis.name] = [axis.map_forward(v) for v in triple]

    normalized_master_locs = [
        fontTools.varLib.models.normalizeLocation(m, internal_axis_supports)
        for m in internal_master_locs
    ]

    # Find base master
    base_idx = None
    for i, m in enumerate(normalized_master_locs):
        if all(v == 0 for v in m.values()):
            assert base_idx is None
            base_idx = i
    assert base_idx is not None, "Base master not found; no master at default location?"

    return fontTools.varLib._DesignSpaceData(
        axes,
        internal_axis_supports,
        base_idx,
        normalized_master_locs,
        masters,
        instances,
        designspace.rules,
    )


if __name__ == "__main__":
    designspace = fontTools.designspaceLib.DesignSpaceDocument.fromfile(
        sys.argv[1]
    )
    vf = generate_variable_font(designspace)
    vf.save("TestVF.ttf")
