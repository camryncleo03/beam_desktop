from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class PointLoad:
    magnitude: float
    position: float


@dataclass(frozen=True)
class UniformLoad:
    magnitude: float
    start: float
    end: float


@dataclass(frozen=True)
class Section:
    name: str
    material: str
    e_ksi: float
    fb_ksi: float
    ix_in4: float
    sx_in3: float
    weight_lbft: float | None = None


STEEL_SECTIONS = (
    Section("W8x10", "Steel", 29000.0, 30.0, 30.8, 7.81, 10.0),
    Section("W10x12", "Steel", 29000.0, 30.0, 53.8, 10.9, 12.0),
    Section("W12x26", "Steel", 29000.0, 30.0, 204.0, 33.4, 26.0),
    Section("W14x22", "Steel", 29000.0, 30.0, 199.0, 29.0, 22.0),
    Section("W16x26", "Steel", 29000.0, 30.0, 301.0, 38.4, 26.0),
    Section("W18x35", "Steel", 29000.0, 30.0, 510.0, 57.6, 35.0),
    Section("W21x44", "Steel", 29000.0, 30.0, 843.0, 81.6, 44.0),
    Section("W24x55", "Steel", 29000.0, 30.0, 1350.0, 114.0, 55.0),
)

LUMBER_SECTIONS = (
    Section("2x8", "Douglas Fir-Larch No. 2", 1600.0, 0.900, 47.63, 13.14),
    Section("2x10", "Douglas Fir-Larch No. 2", 1600.0, 0.900, 98.93, 21.39),
    Section("2x12", "Douglas Fir-Larch No. 2", 1600.0, 0.900, 177.98, 31.64),
)


@dataclass(frozen=True)
class BeamAnalysis:
    support: str
    span_ft: float
    x_ft: np.ndarray
    shear_kips: np.ndarray
    moment_kipft: np.ndarray
    deflection_in: np.ndarray
    left_reaction_kips: float
    right_reaction_kips: float
    fixed_end_moment_kipft: float
    max_shear_kips: float
    max_shear_location_ft: float
    max_moment_kipft: float
    max_moment_location_ft: float
    max_deflection_in: float
    max_deflection_location_ft: float


@dataclass(frozen=True)
class SectionCheck:
    section: Section
    bending_stress_ksi: float
    allowable_bending_ksi: float
    bending_pass: bool
    max_deflection_in: float
    allowable_deflection_in: float
    deflection_pass: bool
    max_moment_location_ft: float
    max_deflection_location_ft: float


def sections_for_material(material: str) -> tuple[Section, ...]:
    if material == "Douglas Fir-Larch No. 2":
        return LUMBER_SECTIONS
    return STEEL_SECTIONS


def clip_uniform_loads(
    loads: Sequence[UniformLoad], span_ft: float
) -> list[UniformLoad]:
    clipped = []
    for load in loads:
        start = max(0.0, min(load.start, span_ft))
        end = max(0.0, min(load.end, span_ft))
        if end > start:
            clipped.append(UniformLoad(load.magnitude, start, end))
    return clipped


def get_reactions(
    support: str,
    span_ft: float,
    point_loads: Sequence[PointLoad],
    uniform_loads: Sequence[UniformLoad],
) -> tuple[float, float, float]:
    in_span_points = [
        load for load in point_loads if 0.0 <= load.position <= span_ft
    ]
    clipped_uniform = clip_uniform_loads(uniform_loads, span_ft)

    point_resultant = sum(load.magnitude for load in in_span_points)
    point_moment = sum(
        load.magnitude * load.position for load in in_span_points
    )

    uniform_resultant = 0.0
    uniform_moment = 0.0
    for load in clipped_uniform:
        total = load.magnitude * (load.end - load.start)
        centroid = (load.start + load.end) / 2.0
        uniform_resultant += total
        uniform_moment += total * centroid

    total_downward = point_resultant + uniform_resultant

    if support == "Cantilever":
        fixed_moment = point_moment + uniform_moment
        return total_downward, 0.0, fixed_moment

    left_reaction = (
        total_downward * span_ft - point_moment - uniform_moment
    ) / span_ft
    right_reaction = total_downward - left_reaction
    return left_reaction, right_reaction, 0.0


def build_x_values(
    span_ft: float,
    point_loads: Sequence[PointLoad],
    uniform_loads: Sequence[UniformLoad],
) -> np.ndarray:
    spacing = np.arange(0.0, span_ft + 0.005, 0.01)
    exact = [0.0, span_ft]
    exact.extend(
        load.position
        for load in point_loads
        if 0.0 <= load.position <= span_ft
    )
    for load in uniform_loads:
        exact.extend(
            position
            for position in (max(0.0, load.start), min(span_ft, load.end))
            if 0.0 <= position <= span_ft
        )
    return np.unique(np.concatenate((spacing, np.array(exact, dtype=float))))


def calculate_internal_forces(
    support: str,
    span_ft: float,
    x_ft: np.ndarray,
    point_loads: Sequence[PointLoad],
    uniform_loads: Sequence[UniformLoad],
) -> tuple[np.ndarray, np.ndarray]:
    in_span_points = [
        load for load in point_loads if 0.0 <= load.position <= span_ft
    ]
    clipped_uniform = clip_uniform_loads(uniform_loads, span_ft)
    left_reaction, _, fixed_moment = get_reactions(
        support, span_ft, point_loads, uniform_loads
    )

    if support == "Cantilever":
        shear = np.full_like(x_ft, left_reaction)
        moment = np.zeros_like(x_ft)
        for load in in_span_points:
            shear -= np.where(x_ft >= load.position, load.magnitude, 0.0)
            moment -= load.magnitude * np.maximum(load.position - x_ft, 0.0)
        for load in clipped_uniform:
            shear -= load.magnitude * np.maximum(
                np.minimum(load.end, span_ft)
                - np.maximum(load.start, x_ft),
                0.0,
            )
            moment -= load.magnitude * (
                np.maximum(load.end - x_ft, 0.0)
                * np.maximum(load.end - x_ft, 0.0)
                / 2.0
                - np.maximum(load.start - x_ft, 0.0)
                * np.maximum(load.start - x_ft, 0.0)
                / 2.0
            )
        return shear, moment

    shear = np.full_like(x_ft, left_reaction)
    moment = left_reaction * x_ft
    for load in in_span_points:
        moment -= load.magnitude * np.maximum(x_ft - load.position, 0.0)
        shear -= np.where(x_ft >= load.position, load.magnitude, 0.0)
    for load in clipped_uniform:
        shear -= load.magnitude * np.where(
            x_ft < load.start,
            0.0,
            np.where(x_ft < load.end, x_ft - load.start, load.end - load.start),
        )
        overlap_end = np.minimum(x_ft, load.end)
        length = np.maximum(overlap_end - load.start, 0.0)
        centroid = load.start + length / 2.0
        moment -= load.magnitude * length * (
            np.maximum(x_ft - centroid, 0.0)
        )
    return shear, moment


def calculate_deflection(
    support: str,
    span_ft: float,
    x_ft: np.ndarray,
    moment_kipft: np.ndarray,
    section: Section,
) -> np.ndarray:
    x_in = x_ft * 12.0
    dx_in = np.diff(x_in)
    moment_kin = moment_kipft * 12.0
    curvature = moment_kin / (section.e_ksi * section.ix_in4)

    midpoint_curvature = (curvature[:-1] + curvature[1:]) / 2.0
    slope = np.zeros_like(x_in)
    slope[1:] = np.cumsum(midpoint_curvature * dx_in)

    deflection = np.zeros_like(x_in)
    midpoint_slope = (slope[:-1] + slope[1:]) / 2.0
    deflection[1:] = np.cumsum(midpoint_slope * dx_in)

    if support == "Simply Supported":
        correction_slope = deflection[-1] / x_in[-1]
        deflection -= correction_slope * x_in

    return deflection


def analyze_beam(
    support: str,
    span_ft: float,
    point_loads: Sequence[PointLoad],
    uniform_loads: Sequence[UniformLoad],
    section: Section,
) -> BeamAnalysis:
    x_ft = build_x_values(span_ft, point_loads, uniform_loads)
    left_reaction, right_reaction, fixed_moment = get_reactions(
        support, span_ft, point_loads, uniform_loads
    )
    shear, moment = calculate_internal_forces(
        support, span_ft, x_ft, point_loads, uniform_loads
    )
    deflection = calculate_deflection(
        support, span_ft, x_ft, moment, section
    )

    max_shear_index = int(np.argmax(np.abs(shear)))
    max_moment_index = int(np.argmax(np.abs(moment)))
    max_deflection_index = int(np.argmax(np.abs(deflection)))

    return BeamAnalysis(
        support=support,
        span_ft=span_ft,
        x_ft=x_ft,
        shear_kips=shear,
        moment_kipft=moment,
        deflection_in=deflection,
        left_reaction_kips=left_reaction,
        right_reaction_kips=right_reaction,
        fixed_end_moment_kipft=fixed_moment,
        max_shear_kips=float(shear[max_shear_index]),
        max_shear_location_ft=float(x_ft[max_shear_index]),
        max_moment_kipft=float(abs(moment[max_moment_index])),
        max_moment_location_ft=float(x_ft[max_moment_index]),
        max_deflection_in=float(abs(deflection[max_deflection_index]) * (
            1.0 if deflection[max_deflection_index] < 0.0 else 1.0
        )),
        max_deflection_location_ft=float(x_ft[max_deflection_index]),
    )


def check_section(
    support: str,
    span_ft: float,
    point_loads: Sequence[PointLoad],
    uniform_loads: Sequence[UniformLoad],
    section: Section,
    deflection_limit: str = "L/360",
) -> SectionCheck:
    analysis = analyze_beam(
        support, span_ft, point_loads, uniform_loads, section
    )
    bending_stress = (
        analysis.max_moment_kipft * 12.0 / section.sx_in3
    )
    allowable_deflection = span_ft * 12.0 / (
        240.0 if deflection_limit == "L/240" else 360.0
    )
    return SectionCheck(
        section=section,
        bending_stress_ksi=bending_stress,
        allowable_bending_ksi=section.fb_ksi,
        bending_pass=bending_stress <= section.fb_ksi,
        max_deflection_in=analysis.max_deflection_in,
        allowable_deflection_in=allowable_deflection,
        deflection_pass=analysis.max_deflection_in <= allowable_deflection,
        max_moment_location_ft=analysis.max_moment_location_ft,
        max_deflection_location_ft=analysis.max_deflection_location_ft,
    )


def find_recommended_section(
    support: str,
    span_ft: float,
    point_loads: Sequence[PointLoad],
    uniform_loads: Sequence[UniformLoad],
    material: str,
    deflection_limit: str = "L/360",
) -> SectionCheck | None:
    passing = []
    for section in sections_for_material(material):
        check = check_section(
            support,
            span_ft,
            point_loads,
            uniform_loads,
            section,
            deflection_limit,
        )
        if check.bending_pass and check.deflection_pass:
            passing.append(check)
    if not passing:
        return None
    if material == "Douglas Fir-Larch No. 2":
        return passing[0]
    return sorted(
        passing,
        key=lambda check: (
            check.section.weight_lbft if check.section.weight_lbft is not None else 0.0,
            -check.section.ix_in4,
        ),
    )[0]
