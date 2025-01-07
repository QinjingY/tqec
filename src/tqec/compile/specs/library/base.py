from typing import Callable

from tqec.compile.block import CompiledBlock
from tqec.compile.specs.base import (
    BlockBuilder,
    CubeSpec,
    PipeSpec,
    Substitution,
    SubstitutionBuilder,
)
from tqec.compile.specs.enums import JunctionArms
from tqec.computation.cube import Port, YCube, ZXCube
from tqec.enums import Basis
from tqec.exceptions import TQECException
from tqec.plaquette.compilation.base import PlaquetteCompiler
from tqec.plaquette.frozendefaultdict import FrozenDefaultDict
from tqec.plaquette.plaquette import Plaquette, Plaquettes
from tqec.plaquette.rpng import RPNGDescription
from tqec.plaquette.translators.default import DefaultRPNGTranslator
from tqec.position import Direction3D
from tqec.templates.enums import ZObservableOrientation
from tqec.templates.indices.base import RectangularTemplate
from tqec.templates.indices.enums import TemplateBorder
from tqec.templates.library.hadamard import get_temporal_hadamard_rpng_descriptions
from tqec.templates.library.memory import (
    get_memory_horizontal_boundary_raw_template,
    get_memory_horizontal_boundary_rpng_descriptions,
    get_memory_qubit_raw_template,
    get_memory_qubit_rpng_descriptions,
    get_memory_vertical_boundary_raw_template,
    get_memory_vertical_boundary_rpng_descriptions,
)
from tqec.templates.library.spatial import (
    get_spatial_junction_arm_raw_template,
    get_spatial_junction_qubit_raw_template,
    get_spatial_junction_qubit_rpng_descriptions,
)


class BaseBlockBuilder(BlockBuilder):
    """Base implementation of the :class:`~tqec.compile.specs.base.BlockBuilder`
    interface.

    This class provides a good enough default implementation that should be
    enough for most of the block builders.
    """

    def __init__(self, compiler: PlaquetteCompiler) -> None:
        """Initialise the :class:`BaseBlockBuilder` with a compiler.

        Args:
            compiler: compiler to transform the plaquettes in the standard
                implementation to a custom implementation.
        """
        self._translator = DefaultRPNGTranslator()
        self._compiler = compiler

    @staticmethod
    def _get_template_and_plaquettes(
        spec: CubeSpec,
    ) -> tuple[RectangularTemplate, list[FrozenDefaultDict[int, RPNGDescription]]]:
        """Get the template and plaquettes corresponding to the provided ``spec``.

        Args:
            spec: specification of the cube we want to implement.

        Returns:
            the template and list of 3 mappings from plaquette indices to RPNG
            descriptions that are needed to implement the cube corresponding to
            the provided ``spec``.
        """
        assert isinstance(spec.kind, ZXCube)
        x, y, z = spec.kind.as_tuple()
        resets_and_measurements = [(z, None), (None, None), (None, z)]
        if not spec.is_spatial_junction:
            orientation = (
                ZObservableOrientation.HORIZONTAL
                if x == Basis.Z
                else ZObservableOrientation.VERTICAL
            )
            return get_memory_qubit_raw_template(), [
                get_memory_qubit_rpng_descriptions(orientation, r, m)
                for r, m in resets_and_measurements
            ]
        # else:
        return get_spatial_junction_qubit_raw_template(), [
            get_spatial_junction_qubit_rpng_descriptions(x, spec.junction_arms, r, m)
            for r, m in resets_and_measurements
        ]

    def __call__(self, spec: CubeSpec) -> CompiledBlock:
        kind = spec.kind
        if isinstance(kind, Port):
            raise TQECException("Cannot build a block for a Port.")
        elif isinstance(kind, YCube):
            raise NotImplementedError("Y cube is not implemented.")
        # else
        template, mappings = BaseBlockBuilder._get_template_and_plaquettes(spec)
        plaquettes = [
            Plaquettes(
                mapping.map_values(
                    lambda descr: self._compiler.compile(
                        self._translator.translate(descr)
                    )
                )
            )
            for mapping in mappings
        ]
        return CompiledBlock(template, plaquettes)


class BaseSubstitutionBuilder(SubstitutionBuilder):
    """Base implementation of the
    :class:`~tqec.compile.specs.base.SubstitutionBuilder` interface.

    This class provides a good enough default implementation that should be
    enough for most of the block builders.
    """

    def __init__(self, compiler: PlaquetteCompiler) -> None:
        """Initialise the :class:`BaseSubstitutionBuilder` with a compiler.

        Args:
            compiler: compiler to transform the plaquettes in the standard
                implementation to a custom implementation.
        """
        self._translator = DefaultRPNGTranslator()
        self._compiler = compiler

    def _get_plaquette(self, description: RPNGDescription) -> Plaquette:
        return self._compiler.compile(self._translator.translate(description))

    def __call__(self, spec: PipeSpec) -> Substitution:
        if spec.pipe_kind.is_temporal:
            return self.get_temporal_pipe_substitution(spec)
        return self.get_spatial_pipe_substitution(spec)

    ##############################
    #    TEMPORAL SUBSTITUTION   #
    ##############################

    def get_temporal_pipe_substitution(self, spec: PipeSpec) -> Substitution:
        """Returns the substitution that should be performed to implement the
        provided ``spec``.

        Args:
            spec: description of the pipe that should be implemented by this
                method. Should be a temporal pipe.

        Raises:
            AssertionError: if ``spec`` does not represent a temporal junction.

        Returns:
            the substitution that should be performed to implement the provided
            ``spec``.
        """
        assert spec.pipe_kind.is_temporal
        if spec.pipe_kind.has_hadamard:
            return self._get_temporal_hadamard_pipe_substitution(spec)
        # Else, it is a regular temporal junction
        return self._get_temporal_non_hadamard_pipe_substitution(spec)

    def _get_temporal_non_hadamard_pipe_substitution(
        self, spec: PipeSpec
    ) -> Substitution:
        """Returns the substitution that should be performed to implement a
        regular temporal junction without Hadamard transition.

        Args:
            spec: description of the pipe that should be implemented by this
                method. Should be a regular (i.e., non-Hadamard) temporal pipe.

        Raises:
            AssertionError: if the provided ``pipe`` is not a temporal pipe, or
                if it contains a Hadamard transition.

        Returns:
            the substitution that should be performed to implement the provided
            ``spec``.
        """
        assert spec.pipe_kind.is_temporal
        assert not spec.pipe_kind.has_hadamard

        z_observable_orientation = (
            ZObservableOrientation.HORIZONTAL
            if spec.pipe_kind.x == Basis.Z
            else ZObservableOrientation.VERTICAL
        )
        memory_descriptions = get_memory_qubit_rpng_descriptions(
            z_observable_orientation
        )
        memory_plaquettes = Plaquettes(
            memory_descriptions.map_values(self._get_plaquette)
        )
        return Substitution({-1: memory_plaquettes}, {0: memory_plaquettes})

    def _get_temporal_hadamard_pipe_substitution(self, spec: PipeSpec) -> Substitution:
        """Returns the substitution that should be performed to implement a
        Hadamard temporal junction.

        Note:
            This method performs the Hadamard transition at the end of the
            layer that appear first (i.e., temporally before the other, or in
            other words the one with a lower Z index).

        Args:
            spec: description of the pipe that should be implemented by this
                method. Should be a Hadamard temporal pipe.

        Raises:
            AssertionError: if the provided ``pipe`` is not a temporal pipe, or
                if it is not a Hadamard transition.

        Returns:
            the substitution that should be performed to implement the provided
            ``spec``.
        """
        assert spec.pipe_kind.is_temporal
        assert spec.pipe_kind.has_hadamard

        #
        x_axis_basis_at_head = spec.pipe_kind.get_basis_along(
            Direction3D.X, at_head=True
        )
        if x_axis_basis_at_head is None:
            raise TQECException(
                "A temporal pipe should have a non-None basis on the X-axis."
            )

        first_layer_orientation: ZObservableOrientation
        second_layer_orientation: ZObservableOrientation
        if x_axis_basis_at_head == Basis.Z:
            first_layer_orientation = ZObservableOrientation.HORIZONTAL
            second_layer_orientation = ZObservableOrientation.VERTICAL
        else:
            first_layer_orientation = ZObservableOrientation.VERTICAL
            second_layer_orientation = ZObservableOrientation.HORIZONTAL
        hadamard_descriptions = get_temporal_hadamard_rpng_descriptions(
            first_layer_orientation
        )
        hadamard_plaquettes = Plaquettes(
            hadamard_descriptions.map_values(self._get_plaquette)
        )

        memory_descriptions = get_memory_qubit_rpng_descriptions(
            second_layer_orientation
        )
        memory_plaquettes = Plaquettes(
            memory_descriptions.map_values(self._get_plaquette)
        )
        return Substitution({-1: hadamard_plaquettes}, {0: memory_plaquettes})

    ##############################
    #    SPATIAL SUBSTITUTION    #
    ##############################

    @staticmethod
    def _get_plaquette_indices_mapping(
        qubit_templates: tuple[RectangularTemplate, RectangularTemplate],
        pipe_template: RectangularTemplate,
        direction: Direction3D,
    ) -> tuple[dict[int, int], dict[int, int]]:
        tb1: TemplateBorder
        tb2: TemplateBorder
        match direction:
            case Direction3D.X:
                tb1 = TemplateBorder.LEFT
                tb2 = TemplateBorder.RIGHT
            case Direction3D.Y:
                tb1 = TemplateBorder.BOTTOM
                tb2 = TemplateBorder.TOP
            case Direction3D.Z:
                raise TQECException("This method cannot be used with a temporal pipe.")

        return (
            pipe_template.get_border_indices(tb1).to(
                qubit_templates[0].get_border_indices(tb2)
            ),
            pipe_template.get_border_indices(tb2).to(
                qubit_templates[1].get_border_indices(tb1)
            ),
        )

    @staticmethod
    def _get_spatial_junction_arm(spec: PipeSpec) -> JunctionArms:
        spatial_junction_is_first: bool = spec.cube_specs[0].is_spatial_junction
        match spatial_junction_is_first, spec.pipe_kind.direction:
            case (True, Direction3D.X):
                return JunctionArms.RIGHT
            case (False, Direction3D.X):
                return JunctionArms.LEFT
            case (True, Direction3D.Y):
                return JunctionArms.UP
            case (False, Direction3D.Y):
                return JunctionArms.DOWN
            case (_, Direction3D.Z):
                raise TQECException(
                    "Should never happen as we are in a spatial (i.e., X/Y plane) junction."
                )

    def _get_spatial_junction_pipe_substitution(self, spec: PipeSpec) -> Substitution:
        assert spec.pipe_kind.is_spatial
        # Check that we do have a spatial junction.
        assert any(spec.is_spatial_junction for spec in spec.cube_specs)
        # For the moment, two spatial junctions side by side are not supported.
        if all(spec.is_spatial_junction for spec in spec.cube_specs):
            raise TQECException(
                "Found 2 spatial junctions connected. This is not supported yet."
            )
        # We are sure we have exactly one spatial junction, se we recover it.
        arm = BaseSubstitutionBuilder._get_spatial_junction_arm(spec)
        xbasis, ybasis = spec.pipe_kind.x, spec.pipe_kind.y
        assert xbasis is not None or ybasis is not None
        spatial_boundary_basis: Basis = xbasis if xbasis is not None else ybasis  # type: ignore
        # Get the plaquette indices mappings
        pipe_template = get_spatial_junction_arm_raw_template(arm)
        mappings = BaseSubstitutionBuilder._get_plaquette_indices_mapping(
            spec.cube_templates, pipe_template, spec.pipe_kind.direction
        )
        # The end goal of this function is to fill in the following 2 variables
        # and use them to make a Substitution instance.
        src_substitution: dict[int, Plaquettes] = {}
        dst_substitution: dict[int, Plaquettes] = {}
        for layer_index, (reset, measurement) in enumerate(
            [(spec.pipe_kind.z, None), (None, None), (None, spec.pipe_kind.z)]
        ):
            rpng_descriptions = get_spatial_junction_qubit_rpng_descriptions(
                spatial_boundary_basis, arm, reset, measurement
            )
            plaquettes = rpng_descriptions.map_values(self._get_plaquette)
            src_substitution[layer_index] = Plaquettes(
                plaquettes.map_keys(lambda i: mappings[0][i])
            )
            dst_substitution[layer_index] = Plaquettes(
                plaquettes.map_keys(lambda i: mappings[1][i])
            )
        return Substitution(src_substitution, dst_substitution)

    def _get_spatial_regular_pipe_substitution(self, spec: PipeSpec) -> Substitution:
        assert all(not spec.is_spatial_junction for spec in spec.cube_specs)
        # Depending on the position of the pipe (basically, is it oriented in the
        # X or Y axis?), we have to change a few variables for later:
        # - the two mappings from the pipe plaquette indices to each of the
        #   provided ``spec.cube_specs`` plaquette indices.
        # - the function that will create the RPNG descriptions.
        # - the Z observable orientation.
        mappings: tuple[dict[int, int], dict[int, int]]
        description_factory: Callable[
            [ZObservableOrientation, Basis | None, Basis | None],
            FrozenDefaultDict[int, RPNGDescription],
        ]
        z_observable_orientation: ZObservableOrientation
        match spec.pipe_kind.direction:
            case Direction3D.X:
                pipe_template = get_memory_vertical_boundary_raw_template()
                mappings = (
                    pipe_template.get_border_indices(TemplateBorder.LEFT).to(
                        spec.cube_templates[0].get_border_indices(TemplateBorder.RIGHT)
                    ),
                    pipe_template.get_border_indices(TemplateBorder.RIGHT).to(
                        spec.cube_templates[1].get_border_indices(TemplateBorder.LEFT)
                    ),
                )
                description_factory = get_memory_vertical_boundary_rpng_descriptions
                z_observable_orientation = (
                    ZObservableOrientation.HORIZONTAL
                    if spec.pipe_kind.y == Basis.X
                    else ZObservableOrientation.VERTICAL
                )
            case Direction3D.Y:
                pipe_template = get_memory_horizontal_boundary_raw_template()
                mappings = (
                    pipe_template.get_border_indices(TemplateBorder.BOTTOM).to(
                        spec.cube_templates[0].get_border_indices(TemplateBorder.TOP)
                    ),
                    pipe_template.get_border_indices(TemplateBorder.TOP).to(
                        spec.cube_templates[1].get_border_indices(TemplateBorder.BOTTOM)
                    ),
                )
                description_factory = get_memory_horizontal_boundary_rpng_descriptions
                z_observable_orientation = (
                    ZObservableOrientation.HORIZONTAL
                    if spec.pipe_kind.x == Basis.Z
                    else ZObservableOrientation.VERTICAL
                )
            case Direction3D.Z:
                raise TQECException(
                    "Spatial pipes cannot have a direction equal to Direction3D.Z."
                )
        # The end goal of this function is to fill in the following 2 variables
        # and use them to make a Substitution instance.
        src_substitution: dict[int, Plaquettes] = {}
        dst_substitution: dict[int, Plaquettes] = {}
        for layer_index, (reset, measurement) in enumerate(
            [(spec.pipe_kind.z, None), (None, None), (None, spec.pipe_kind.z)]
        ):
            rpng_descriptions = description_factory(
                z_observable_orientation, reset, measurement
            )
            plaquettes = rpng_descriptions.map_values(self._get_plaquette)
            src_substitution[layer_index] = Plaquettes(
                plaquettes.map_keys(lambda i: mappings[0][i])
            )
            dst_substitution[layer_index] = Plaquettes(
                plaquettes.map_keys(lambda i: mappings[1][i])
            )
        return Substitution(src_substitution, dst_substitution)

    def get_spatial_pipe_substitution(self, spec: PipeSpec) -> Substitution:
        assert spec.pipe_kind.is_spatial
        return (
            self._get_spatial_junction_pipe_substitution(spec)
            if spec.cube_specs[0].is_spatial_junction
            else self._get_spatial_regular_pipe_substitution(spec)
        )
