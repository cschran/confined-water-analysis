import numpy as np
import sys
from tqdm.notebook import tqdm

sys.path.append("../")
from confined_water import utils


def compute_spatial_distribution_of_atoms_on_interface(
    position_universe,
    topology,
    spatial_extent_contact_layer: float,
    pbc_indices,
    start_frame: int,
    end_frame: int,
    frame_frequency: int,
    tube_radius: float = None,
    tube_length_in_unit_cells: int = None,
):
    """
    Compute distribution of atomic positions on interface.
    Arguments:
        position_universes : MDAnalysis universes to be analysed.
        topology : ASE atoms object containing information about topology.
        spatial_extent_contact_layer (float): How far ranges the water contact layer.
        pbc_indices : Direction indices in which system is periodic
        start_frame (int) : Start frame for analysis.
        end_frame (int) : End frame for analysis.
        frame_frequency (int): Take every nth frame only.

    """

    if len(pbc_indices) == 1:

        # compute probabilities for tube
        return _compute_distribution_for_system_with_one_periodic_direction(
            position_universe,
            topology,
            spatial_extent_contact_layer,
            tube_radius,
            tube_length_in_unit_cells,
            pbc_indices,
            start_frame,
            end_frame,
            frame_frequency,
        )

    else:
        # compute probabilities for flat interface
        return _compute_distribution_for_system_with_two_periodic_directions(
            position_universe,
            topology,
            spatial_extent_contact_layer,
            pbc_indices,
            start_frame,
            end_frame,
            frame_frequency,
        )


def _compute_distribution_for_system_with_one_periodic_direction(
    universe,
    topology,
    spatial_extent_contact_layer: float,
    tube_radius: float,
    tube_length_in_unit_cells: int,
    pbc_indices,
    start_frame: int,
    end_frame: int,
    frame_frequency: int,
):
    """
    Compute distribution of atomic positions for 1D systems.
    Arguments:
        universe : MDAnalysis universes to be analysed.
        topology : ASE atoms object containing information about topology.
        spatial_extent_contact_layer (float): How far ranges the water contact layer.
        tube_radius (float) : radius of the tube in A.
        tube_length_in_unit_cells (int): multiples of tube unit cell in periodic direction.
        pbc_indices : Direction indices in which system is periodic
        start_frame (int) : Start frame for analysis.
        end_frame (int) : End frame for analysis.
        frame_frequency (int): Take every nth frame only.

    """
    # define dimensions not periodic, indices
    not_pbc_indices = list(set(pbc_indices) ^ set([0, 1, 2]))
    periodic_vector = np.zeros(3)
    periodic_vector[pbc_indices] = 1

    # wrap atoms in box
    # universe.atoms.pack_into_box(box=topology.get_cell_lengths_and_angles(), inplace=True)

    # start by separating solid atoms from liquid atoms
    solid_atoms = universe.select_atoms("name B N C Na Cl")
    liquid_atoms = universe.select_atoms("name O H")

    # this will serve as our anchor for translation for computing the free energy profile
    anchor_coordinates = solid_atoms.center_of_mass()

    # define reference atoms which will be used to determine rotation
    indices_atoms_anchor_rotation = _get_atom_ids_on_same_tube_axis(
        solid_atoms, tube_length_in_unit_cells, not_pbc_indices
    )

    # compute circumference based on diameter
    tube_circumference = 2 * np.pi * tube_radius

    # define arrays where the coordinates of oxygens and solid atoms will be saved in
    liquid_contact_coord1 = []
    liquid_contact_coord2 = []
    solid_coord1 = []
    solid_coord2 = []

    # solid_1 = np.zeros((int((end_frame - start_frame) / frame_frequency), len(solid_atoms), 2))

    # Loop over trajectory
    for count_frames, frames in enumerate(
        tqdm((universe.trajectory[start_frame:end_frame])[::frame_frequency])
    ):

        # we start by making the frames translationally and rotationally invariant
        # 1. Translations
        # This is done by computing the translation and substracting it

        # solid
        translation_from_frame0 = solid_atoms.center_of_mass() - anchor_coordinates
        universe.atoms.positions -= translation_from_frame0

        # 2. Rotations (only relevant for nanotubes obviously)

        # to enable an easy rotation, translate atoms to COM
        COM = universe.atoms.center_of_mass()
        universe.atoms.positions -= COM

        # prepare everything to compute angle between axis and anchor axis
        solid_axis = np.mean(
            solid_atoms.positions[indices_atoms_anchor_rotation][:, not_pbc_indices],
            axis=0,
        )

        # define normed dot product
        normed_dot_product = np.clip(
            np.dot(
                solid_axis,
                np.asarray([1, 0]),
            )
            / np.linalg.norm(solid_axis),
            -1.0,
            1.0,
        )

        # Compute angle between reference atom and axis perpendicular to periodic axis
        # note we need the negative angle if above 180 degrees
        angle_anchor_first_axis = (
            np.arccos(normed_dot_product) if solid_axis[1] <= 0 else -np.arccos(normed_dot_product)
        )

        # get rotation matrix for periodic axis and computed angle
        rotation_matrix = utils.rotation_matrix(periodic_vector, +angle_anchor_first_axis)

        # rotate atoms, so that this can be compared
        universe.atoms.positions = np.matmul(rotation_matrix, universe.atoms.positions.T).T

        # translate now back to center of mass
        universe.atoms.positions += COM

        # wrap atoms in box
        universe.atoms.pack_into_box(box=topology.get_cell_lengths_and_angles(), inplace=True)

        # define center of mass of solid now
        solid_COM = solid_atoms.center_of_mass()

        # now compute vector from liquid atoms from the center axis of the solid
        vector_liquid_to_central_axis = liquid_atoms.positions - solid_COM

        # only choose those atoms which are within contact layer from solid
        liquid_atoms_in_contact_positions = vector_liquid_to_central_axis[
            np.where(
                np.linalg.norm(vector_liquid_to_central_axis[:, not_pbc_indices], axis=1)
                >= spatial_extent_contact_layer
            )
        ]

        # for chosen atoms compute position in periodic and angular direction
        # periodic is easy
        liquid_contact_coord1 = np.append(
            liquid_contact_coord1,
            liquid_atoms_in_contact_positions[:, pbc_indices] + solid_COM[pbc_indices],
        )

        # the angular coordinate is a bit more tricky
        # start by computing angle from axis
        angles_liquid_contact_central_axis = np.arctan2(
            liquid_atoms_in_contact_positions[:, not_pbc_indices[1]],
            liquid_atoms_in_contact_positions[:, not_pbc_indices[0]],
        )

        # compute expansion on opened tube (adding pi to get only positive values)
        angular_component_liquid_contact = (
            tube_circumference * (angles_liquid_contact_central_axis + np.pi) / (2 * np.pi)
        )
        liquid_contact_coord2 = np.append(liquid_contact_coord2, angular_component_liquid_contact)

        # do the same thing for solid
        vector_solid_to_central_axis = solid_atoms.positions - solid_COM
        solid_coord1 = np.append(solid_coord1, solid_atoms.positions[:, pbc_indices])

        angles_solid_central_axis = np.arctan2(
            vector_solid_to_central_axis[:, not_pbc_indices[1]],
            vector_solid_to_central_axis[:, not_pbc_indices[0]],
        )

        angular_component_solid = (
            tube_circumference * (angles_solid_central_axis + np.pi) / (2 * np.pi)
        )

        solid_coord2 = np.append(solid_coord2, angular_component_solid)

    # stack everything
    liquid_contact_2d = np.column_stack((liquid_contact_coord1, liquid_contact_coord2))
    solid_2d = np.column_stack((solid_coord1, solid_coord2))

    return liquid_contact_2d, solid_2d


def _compute_distribution_for_system_with_two_periodic_directions(
    universe,
    topology,
    spatial_extent_contact_layer: float,
    pbc_indices,
    start_frame: int,
    end_frame: int,
    frame_frequency: int,
):
    """
    Compute distribution of atomic positions for 2D systems.
    Arguments:
        position_universes : MDAnalysis universe to be analysed.
        topology : ASE atoms object containing information about topology.
        spatial_extent_contact_layer (float): How far ranges the water contact layer.
        pbc_indices : Direction indices in which system is periodic
        start_frame (int) : Start frame for analysis.
        end_frame (int) : End frame for analysis.
        frame_frequency (int): Take every nth frame only.
    Returns:
        liquid_contact_2D: numpy array with positions in periodic directions of
                            oxygens in contact layer
        solid_all: numpy array of all solid atom positions in periodic directions
                     structured by timestep

    """

    # define dimensions not periodic, indices
    not_pbc_indices = list(set(pbc_indices) ^ set([0, 1, 2]))
    periodic_vector = np.zeros(3)
    periodic_vector[pbc_indices] = 1

    # wrap atoms in box
    universe.atoms.pack_into_box(box=topology.get_cell_lengths_and_angles(), inplace=True)

    # start by separating solid atoms from liquid atoms
    solid_atoms = universe.select_atoms("name B N C Na Cl")

    # approximate water with oxygens here
    liquid_atoms = universe.select_atoms("name O")

    # this will serve as our anchor for computing the free energy profile
    anchor_coordinates = universe.atoms.center_of_mass()

    # define arrays where the coordinates of oxygens and solid atoms will be saved in
    liquid_contact_coord1 = []
    liquid_contact_coord2 = []
    solid_all = np.zeros((int((end_frame - start_frame) / frame_frequency), len(solid_atoms), 2))

    # Loop over trajectory
    for count_frames, frames in enumerate(
        tqdm((universe.trajectory[start_frame:end_frame])[::frame_frequency])
    ):
        # wrap atoms in box
        universe.atoms.pack_into_box(box=topology.get_cell_lengths_and_angles(), inplace=True)

        # we start by making the frames translationally invariant
        # This is done by computing the translation and substracting it
        translation_from_frame0 = universe.atoms.center_of_mass() - anchor_coordinates
        universe.atoms.positions -= translation_from_frame0

        # wrap atoms in box
        universe.atoms.pack_into_box(box=topology.get_cell_lengths_and_angles(), inplace=True)

        # define center of mass of solid now
        solid_COM = solid_atoms.center_of_mass()

        # now compute distance from liquid atoms perpendicular to the center of mass of the solid
        perpendicular_distance_liquid_to_solid = (
            liquid_atoms.positions[:, not_pbc_indices] - solid_COM[not_pbc_indices]
        ).flatten()

        # only choose those atoms which are within contact layer only 2D
        liquid_atoms_in_contact_positions = liquid_atoms[
            np.where(perpendicular_distance_liquid_to_solid <= spatial_extent_contact_layer)
        ].positions[:, pbc_indices]

        # save liquid
        liquid_contact_coord1 = np.append(
            liquid_contact_coord1, liquid_atoms_in_contact_positions[:, pbc_indices[0]]
        )

        liquid_contact_coord2 = np.append(
            liquid_contact_coord2, liquid_atoms_in_contact_positions[:, pbc_indices[1]]
        )

        # save solid
        solid_all[count_frames] = solid_atoms.positions[:, pbc_indices]

    # put coords of liquid together
    liquid_contact_2d = np.column_stack((liquid_contact_coord1, liquid_contact_coord2))

    return liquid_contact_2d, np.concatenate(solid_all)


def _get_atom_ids_on_same_tube_axis(solid_atoms, tube_length_in_unit_cells: int, not_pbc_indices):
    """
    Compute axis through atoms of tube parallel to tube axis..
    Arguments:
        solid_atoms: All atoms (including positions) of the tube.
        tube_length_in_unit_cells (int): Length of the tube expressed in multiples of unit cell
        not_pbc_indices: List of ints which are not periodic.
    Returns:
        ids_atoms_on_axis = list of atom ids on the same axis

    """

    # for atom 0 get all indices of atoms which have similar coordinates in the non-pbc directions
    ids_candidate_atoms_on_axis_with_0 = np.argsort(
        np.linalg.norm(
            solid_atoms.positions[:, not_pbc_indices] - solid_atoms.positions[0][not_pbc_indices],
            axis=1,
        )
    )

    # return indices closest based on tube length
    return ids_candidate_atoms_on_axis_with_0[0 : 2 * tube_length_in_unit_cells]
