#!/usr/bin/env python3
"""Merge Neurolucida/MBF XML annotations from two folders.

The XML files in ``primary_folder`` provide the output filename and all of the
document metadata/header (including the image filename).  Their annotations
are retained, after every primary-file point's ``x`` and ``y`` coordinates are
divided by that file's own ``<scale x="..." y="..."/>`` values.  Annotation elements from the matched file in
``contour_folder`` are then added to that primary XML.

Usage
-----
python combine_mbf_xml.py PRIMARY_FOLDER CONTOUR_FOLDER OUTPUT_FOLDER

For example:
python combine_mbf_xml.py "D:/lab data/cell mappings" \
    "D:/lab data/Segmentations" "D:/lab data/combined xml"

Files are paired by a normalized filename.  This deliberately ignores terms
such as ``Finished``, ``DAPI``, image-channel numbers, and ``TISSUE``.  Thus,
``MM463 LH B25_Finished.xml`` is paired with
``MM463 LH_DAPI_B25_488_555_DAPI_FULL TISSUE.xml``.  If a pair is ambiguous
or missing, the script reports it and does not create an output file for it.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


# These root-level elements describe the document rather than an annotation.
# They must come solely from the primary ("Finished") file.
METADATA_TAGS = {
    "description",
    "descriptionname",
    "descriptionstudy",
    "descriptionanimal",
    "descriptionnotes",
    "filefacts",
    "property",
    "images",
    "thumbnail",
}

# Filename words that distinguish the two source types but do not identify a
# tissue section.  Add a word here if your naming scheme adds another such tag.
IGNORED_NAME_TOKENS = {
    "finished",
    "dapi",
    "full",
    "tissue",
    "contour",
    "contours",
    "cr",
    "segmentation",
    "segmentations",
}


def local_name(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def matching_key(xml_path: Path) -> str:
    """Create a stable matching key from differently decorated XML filenames."""
    stem = re.sub(r"\s*\(\d+\)\s*$", "", xml_path.stem.casefold())
    tokens = re.findall(r"[a-z]+\d*|\d+", stem)

    kept: list[str] = []
    for token in tokens:
        if token in IGNORED_NAME_TOKENS:
            continue
        # Standalone numeric tokens are image channel labels (for example
        # _488_555_) rather than the specimen/section identifier B25.
        if token.isdigit():
            continue
        kept.append(token)

    if not kept:
        raise ValueError("filename has no usable matching tokens")
    return "_".join(kept)


def xml_files(folder: Path) -> list[Path]:
    """Return XML files in one folder (not recursively), case-insensitively."""
    return sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.casefold() == ".xml"),
        key=lambda path: path.name.casefold(),
    )


def make_key_index(files: list[Path]) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        index[matching_key(path)].append(path)
    return index


def annotation_elements(root: ET.Element) -> list[ET.Element]:
    """Return root children that are annotations, not document metadata."""
    return [child for child in root if local_name(child.tag) not in METADATA_TAGS]


def primary_point_scale(root: ET.Element) -> tuple[float, float]:
    """Read the single image-coordinate scale stored in a primary MBF XML."""
    scales = [element for element in root.iter() if local_name(element.tag) == "scale"]
    if len(scales) != 1:
        raise ValueError(f"expected exactly one <scale> element, found {len(scales)}")

    try:
        scale_x = float(scales[0].attrib["x"])
        scale_y = float(scales[0].attrib["y"])
    except (KeyError, ValueError) as exc:
        raise ValueError("the primary XML <scale> element needs numeric x and y attributes") from exc

    if scale_x <= 0 or scale_y <= 0:
        raise ValueError("the primary XML <scale> values must be greater than zero")
    return scale_x, scale_y


def scale_primary_points(root: ET.Element, scale_x: float, scale_y: float) -> int:
    """Normalize every primary point x/y coordinate by its image scale."""
    scaled = 0
    for element in root.iter():
        if local_name(element.tag) != "point":
            continue
        try:
            element.set("x", f"{float(element.attrib['x']) / scale_x:.6f}")
            element.set("y", f"{float(element.attrib['y']) / scale_y:.6f}")
        except (KeyError, ValueError) as exc:
            raise ValueError("every <point> in the primary XML needs numeric x and y attributes") from exc
        scaled += 1
    return scaled


def merge_xml(primary_path: Path, contour_path: Path, output_path: Path) -> tuple[int, int, int, float, float]:
    """Create one merged XML and return counts of retained and added elements."""
    primary_tree = ET.parse(primary_path)
    contour_tree = ET.parse(contour_path)
    primary_root = primary_tree.getroot()
    contour_root = contour_tree.getroot()

    if local_name(primary_root.tag) != "mbf" or local_name(contour_root.tag) != "mbf":
        raise ValueError("both files must have an <mbf> root element")

    scale_x, scale_y = primary_point_scale(primary_root)
    scaled_points = scale_primary_points(primary_root, scale_x, scale_y)
    retained = len(annotation_elements(primary_root))
    additions = annotation_elements(contour_root)
    # deepcopy is required: an Element can have only one parent in a tree.
    primary_root.extend(copy.deepcopy(additions))

    namespace = primary_root.tag.partition("}")[0].lstrip("{")
    if namespace:
        ET.register_namespace("", namespace)

    ET.indent(primary_tree, space="  ")
    primary_tree.write(output_path, encoding="ISO-8859-1", xml_declaration=True)
    return retained, len(additions), scaled_points, scale_x, scale_y


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge MBF XML annotations folder-by-folder while preserving the "
            "primary files' header and filenames."
        )
    )
    parser.add_argument(
        "primary_folder",
        type=Path,
        help="Folder of Finished/cell-mapping XML files whose header and names are retained.",
    )
    parser.add_argument(
        "contour_folder",
        type=Path,
        help="Folder of contour/segmentation XML files to add.",
    )
    parser.add_argument("output_folder", type=Path, help="Folder where merged XML files are written.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for folder, label in ((args.primary_folder, "primary"), (args.contour_folder, "contour")):
        if not folder.is_dir():
            print(f"Error: {label} folder does not exist or is not a folder: {folder}", file=sys.stderr)
            return 2

    primary_files = xml_files(args.primary_folder)
    contour_files = xml_files(args.contour_folder)
    if not primary_files:
        print(f"Error: no XML files found in primary folder: {args.primary_folder}", file=sys.stderr)
        return 2
    if not contour_files:
        print(f"Error: no XML files found in contour folder: {args.contour_folder}", file=sys.stderr)
        return 2

    try:
        contour_index = make_key_index(contour_files)
    except ValueError as exc:
        print(f"Error while reading contour filenames: {exc}", file=sys.stderr)
        return 2

    args.output_folder.mkdir(parents=True, exist_ok=True)
    merged = 0
    skipped = 0

    for primary_path in primary_files:
        try:
            key = matching_key(primary_path)
        except ValueError as exc:
            print(f"SKIPPED {primary_path.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        matches = contour_index.get(key, [])
        if len(matches) != 1:
            reason = "no matching contour XML" if not matches else "multiple matching contour XML files"
            names = ", ".join(match.name for match in matches)
            detail = f" ({names})" if names else ""
            print(f"SKIPPED {primary_path.name}: {reason}{detail}", file=sys.stderr)
            skipped += 1
            continue

        output_path = args.output_folder / primary_path.name
        try:
            retained, added, scaled_points, scale_x, scale_y = merge_xml(primary_path, matches[0], output_path)
        except (ET.ParseError, OSError, ValueError) as exc:
            print(f"SKIPPED {primary_path.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        print(
            f"MERGED {primary_path.name} + {matches[0].name} -> {output_path.name} "
            f"(divided {scaled_points} primary point(s) by x={scale_x:g}, y={scale_y:g}; "
            f"kept {retained} primary annotation element(s), added {added})"
        )
        merged += 1

    print(f"Done: {merged} merged, {skipped} skipped.")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
