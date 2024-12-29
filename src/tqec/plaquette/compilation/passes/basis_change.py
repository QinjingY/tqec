import stim
from typing_extensions import override

from tqec.circuit.instructions import (
    is_combined_reset_and_measurement_instruction,
    is_measurement_instruction,
    is_reset_instruction,
)
from tqec.circuit.moment import Moment, iter_stim_circuit_without_repeat_by_moments
from tqec.exceptions import TQECException
from tqec.plaquette.compilation.passes.base import CompilationPass
from tqec.plaquette.enums import MeasurementBasis, ResetBasis


class ChangeBasisPass(CompilationPass):
    def __init__(self, basis: ResetBasis | MeasurementBasis):
        super().__init__()
        self._basis = basis

    @property
    def change_reset_basis(self) -> bool:
        return isinstance(self._basis, ResetBasis)

    @property
    def change_measurement_basis(self) -> bool:
        return isinstance(self._basis, MeasurementBasis)

    def may_have_to_change(self, instruction: stim.CircuitInstruction) -> bool:
        if self.change_measurement_basis:
            return is_measurement_instruction(instruction)
        return is_reset_instruction(instruction)

    @staticmethod
    def _get_instruction_basis(
        instruction: stim.CircuitInstruction,
    ) -> ResetBasis | MeasurementBasis:
        match instruction.name:
            case "M" | "MZ":
                return MeasurementBasis.Z
            case "MX":
                return MeasurementBasis.X
            case "R" | "RZ":
                return ResetBasis.Z
            case "RX":
                return ResetBasis.X
            case _:
                raise TQECException(
                    f"Found a {instruction.name} instruction, that is not " "supported."
                )

    def _with_basis_changed(self, circuit: stim.Circuit) -> stim.Circuit:
        ret_moments: list[Moment] = []
        for moment in iter_stim_circuit_without_repeat_by_moments(circuit):
            current_moment = stim.Circuit()
            basis_change_moment = stim.Circuit()
            for instruction in moment.instructions:
                if not self.may_have_to_change(instruction):
                    current_moment.append(instruction)
                    continue
                elif is_combined_reset_and_measurement_instruction(instruction):
                    raise TQECException(
                        "Combined reset and measurement instructions are not "
                        f"supported. Found {instruction.name}."
                    )
                # Else, change the reset instruction to the correct basis.
                current_measurement_basis = ChangeBasisPass._get_instruction_basis(
                    instruction
                )
                if current_measurement_basis == self._basis:
                    current_moment.append(instruction)
                else:
                    basis_change_moment.append("H", instruction.targets_copy(), [])
                    current_moment.append(
                        self._basis.instruction_name,
                        instruction.targets_copy(),
                        instruction.gate_args_copy(),
                    )

            if basis_change_moment and self.change_measurement_basis:
                ret_moments.append(Moment(basis_change_moment, _avoid_checks=True))
            ret_moments.append(
                Moment(
                    current_moment,
                    used_qubits=moment.qubits_indices,
                    _avoid_checks=True,
                )
            )
            if basis_change_moment and self.change_reset_basis:
                ret_moments.append(Moment(basis_change_moment, _avoid_checks=True))

        ret_circuit = stim.Circuit()
        for moment in ret_moments[:-1]:
            ret_circuit += moment.circuit
            ret_circuit.append("TICK")
        if ret_moments:
            ret_circuit += ret_moments[-1].circuit
        return ret_circuit

    @override
    def run(self, circuit: stim.Circuit, check_all_flows: bool = False) -> stim.Circuit:
        modified_circuit = self._with_basis_changed(circuit)
        if check_all_flows:
            self.check_flows(circuit, modified_circuit)
        return modified_circuit
