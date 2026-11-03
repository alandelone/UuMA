with open('src/uuma/orbit_runner.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_get_run = """        try:
            orbit_data = orbits.get(orbit_id)
            existing = orbit_data.get("orbit", {}).get("uuma_run_id")
            if existing:
                if isinstance(control_plane, ControlClient):
                    bound = control_plane.require_run(str(existing))
                    if bound.get("agent_id") != "wisdom-oldman":
                        raise PermissionError("Question Orbit Run belongs to another Agent")
                    if bound.get("status") not in {"PENDING", "RUNNING"}:
                        return None
                return str(existing)
            question = knowledge._require("questions", cycle["question_id"])["text"]
            return _ensure_runner_run(control_plane, orbit_id, question)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed resolving run_id for ChatGPT discovery: %s", exc)
            return None"""

new_get_run = """        try:
            orbit_data = orbits.get(orbit_id)
            existing = orbit_data.get("orbit", {}).get("uuma_run_id")
            if existing:
                try:
                    if isinstance(control_plane, ControlClient):
                        bound = control_plane.require_run(str(existing))
                        if bound.get("agent_id") != "wisdom-oldman":
                            raise PermissionError("Question Orbit Run belongs to another Agent")
                        if bound.get("status") in {"PENDING", "RUNNING"}:
                            return str(existing)
                    else:
                        with control_plane.connect() as db:
                            row = db.execute(
                                "SELECT run_id FROM runs WHERE run_id = ? "
                                "AND agent_id = 'wisdom-oldman' "
                                "AND status IN ('PENDING', 'RUNNING')",
                                (existing,),
                            ).fetchone()
                            if row:
                                return str(row["run_id"])
                except Exception as lookup_err:
                    LOGGER.warning("Existing run_id %s not active/reusable (%s); acquiring fresh run", existing, lookup_err)
            question = knowledge._require("questions", cycle["question_id"])["text"]
            fresh_run = _ensure_runner_run(control_plane, orbit_id, question)
            if fresh_run and fresh_run != existing:
                try:
                    with knowledge.store.transaction() as conn:
                        before = knowledge._require("question_orbits", orbit_id, conn)
                        if before.get("uuma_run_id") != fresh_run:
                            orbits._update(
                                conn,
                                "question_orbits",
                                before,
                                before | {"uuma_run_id": fresh_run, "updated_at": datetime.now(UTC).isoformat()},
                                "QUESTION_ORBIT_RUN_BOUND",
                                "wisdom-oldman",
                            )
                except Exception as update_err:
                    LOGGER.warning("Could not persist updated uuma_run_id on orbit: %s", update_err)
            return fresh_run
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed resolving run_id for ChatGPT discovery: %s", exc)
            return None"""

assert old_get_run in c, 'old_get_run not found'
c = c.replace(old_get_run, new_get_run)

old_cursor = """        if cursor:
            cycle_explanation["discovery_state"] = cursor
            attempted = set(cursor.get("attempted_providers") or [])
            cycle_explanation["untried_paths"] = [
                name for name in cycle_explanation.get("untried_paths", [])
                if name not in attempted
            ]"""

new_cursor = """        if cursor:
            cycle_explanation["discovery_state"] = cursor
            attempted = set(cursor.get("attempted_providers") or [])
            next_tier = cursor.get("next_tier", 1)
            if next_tier == 1:
                cycle_explanation["untried_paths"] = [
                    name for name in cycle_explanation.get("untried_paths", [])
                    if name not in attempted
                ]"""

assert old_cursor in c, 'old_cursor not found'
c = c.replace(old_cursor, new_cursor)

with open('src/uuma/orbit_runner.py', 'w', encoding='utf-8', newline='') as f:
    f.write(c)
print("Successfully patched orbit_runner.py")
