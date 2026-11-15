def decay_entries(entries, *, current_tick, summary_after, inaccessible_after):
    output = []
    for original in entries:
        entry = dict(original)
        if entry.get("protected_by"):
            output.append(entry); continue
        age = current_tick - entry.get("last_access_tick", current_tick)
        if age >= inaccessible_after:
            entry["access_state"] = "inaccessible"
        elif age >= summary_after and entry.get("access_state") == "detail":
            entry["access_state"] = "summary"
        output.append(entry)
    return output


def cleanup_entries(entries, *, referenced_ids):
    return [entry for entry in entries if entry.get("protected_by") or
            (entry.get("memory_id") in referenced_ids and entry.get("access_state") != "inaccessible")]
