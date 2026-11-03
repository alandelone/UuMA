with open('src/uuma/question_orbit.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_block = """            untried = exp_dict.get("untried_paths") or []
            blocked_paths = exp_dict.get("blocked_paths") or []

            if satisfied:
                orbit_status = OrbitStatus.COMPLETED
                run_status = ResearchRunStatus.COMPLETED
                stop_reason = "Knowledge satisfaction reached and no HIGH frontier remains."
            elif exhausted:
                orbit_status = OrbitStatus.BUDGET_EXHAUSTED
                run_status = ResearchRunStatus.BUDGET_EXHAUSTED
                stop_reason = "Today's configured research ceiling is reached; waiting for " + budget["reset_at"]
            elif quota_retry_after_seconds:
                orbit_status = OrbitStatus.QUEUED
                run_status = ResearchRunStatus.ACTIVE
                stop_reason = "Provider quota/rate limit; progress saved, waiting before retry."
            elif not open_frontier:
                orbit_status = OrbitStatus.BLOCKED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = "No open research frontier remains while knowledge is still incomplete."
            elif blocked_paths and not untried and no_new_source:
                orbit_status = OrbitStatus.BLOCKED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = f"All available discovery providers are blocked ({', '.join(blocked_paths)}); awaiting credentials or quota recovery."
            elif no_new_source and not untried and open_frontier and all(
                int(item.get("no_source_attempts", 0)) >= 2 for item in open_frontier
            ):
                orbit_status = OrbitStatus.PAUSED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = (
                    exp_dict.get("summary")
                    or "已检索所有未解决问题且全部可用渠道均未找到直接相关资料；成果与缺口已保留。"
                )
            else:
                orbit_status = OrbitStatus.QUEUED
                run_status = ResearchRunStatus.ACTIVE
                stop_reason = None"""

new_block = """            untried = exp_dict.get("untried_paths") or []
            blocked_paths = exp_dict.get("blocked_paths") or []
            next_tier = (exp_dict.get("discovery_state") or {}).get("next_tier", 1)
            deeper_tiers_remain = next_tier in {2, 3, 4}

            if satisfied:
                orbit_status = OrbitStatus.COMPLETED
                run_status = ResearchRunStatus.COMPLETED
                stop_reason = "Knowledge satisfaction reached and no HIGH frontier remains."
            elif exhausted:
                orbit_status = OrbitStatus.BUDGET_EXHAUSTED
                run_status = ResearchRunStatus.BUDGET_EXHAUSTED
                stop_reason = "Today's configured research ceiling is reached; waiting for " + budget["reset_at"]
            elif quota_retry_after_seconds:
                orbit_status = OrbitStatus.QUEUED
                run_status = ResearchRunStatus.ACTIVE
                stop_reason = "Provider quota/rate limit; progress saved, waiting before retry."
            elif not open_frontier:
                orbit_status = OrbitStatus.BLOCKED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = "No open research frontier remains while knowledge is still incomplete."
            elif blocked_paths and not untried and not deeper_tiers_remain and no_new_source:
                orbit_status = OrbitStatus.BLOCKED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = f"All available discovery providers are blocked ({', '.join(blocked_paths)}); awaiting credentials or quota recovery."
            elif no_new_source and not untried and not deeper_tiers_remain and open_frontier and all(
                int(item.get("no_source_attempts", 0)) >= 2 for item in open_frontier
            ):
                orbit_status = OrbitStatus.PAUSED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = (
                    exp_dict.get("summary")
                    or "已检索所有未解决问题且全部可用渠道均未找到直接相关资料；成果与缺口已保留。"
                )
            else:
                orbit_status = OrbitStatus.QUEUED
                run_status = ResearchRunStatus.ACTIVE
                stop_reason = None"""

assert old_block in c, "old_block not found in question_orbit.py"
c = c.replace(old_block, new_block)
with open('src/uuma/question_orbit.py', 'w', encoding='utf-8', newline='') as f:
    f.write(c)
print("Successfully patched question_orbit.py")
