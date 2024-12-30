from tqec.plaquette.compilation.passes.transformer import (
    InstructionCreator,
    ScheduledCircuitTransformation,
    ScheduledCircuitTransformationPass,
    ScheduleOffset,
)
from tqec.plaquette.enums import Basis


class ChangeMeasurementBasisPass(ScheduledCircuitTransformationPass):
    def __init__(self, basis: Basis):
        ibasis = Basis.X if basis == Basis.Z else Basis.Z
        transformations = [
            ScheduledCircuitTransformation(
                f"M{ibasis.value.upper()}",
                {
                    ScheduleOffset(-1): [InstructionCreator("H")],
                    ScheduleOffset(0): [InstructionCreator(f"M{basis.value.upper()}")],
                },
            )
        ]
        if basis == Basis.X:
            transformations.append(
                ScheduledCircuitTransformation(
                    "M",
                    {
                        ScheduleOffset(-1): [InstructionCreator("H")],
                        ScheduleOffset(0): [InstructionCreator("MX")],
                    },
                )
            )
        super().__init__(transformations)
