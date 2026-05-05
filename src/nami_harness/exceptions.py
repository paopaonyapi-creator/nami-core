class HarnessError(Exception):
    pass


class RailDenied(HarnessError):
    pass


class BrakeEngaged(HarnessError):
    pass


class QualityGateFailed(HarnessError):
    pass
