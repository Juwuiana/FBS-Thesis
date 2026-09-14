def get_current_patient_id():
    """
    TODO(auth): replace this with the real logged-in patient's internal
    id once the auth branch merges, e.g.:

        from flask import session
        return session.get("patient_id")

    Raises on purpose for now. A route that silently fell back to a
    hardcoded/default patient_id would show one patient's private FBS
    results to anyone who visits the page -- that failure mode is worse
    than the page simply not working yet.
    """
    raise NotImplementedError(
        "Patient authentication isn't wired in yet. See the auth branch "
        "for the real session lookup -- patient_controller.py just needs "
        "get_current_patient_id() to return the logged-in patient's id."
    )