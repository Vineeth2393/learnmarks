package app.learnmarks.data

/**
 * How a new phone change combines with what is already waiting in the outbox (DESIGN §7).
 * Pure functions, so the rules are unit-tested without a device.
 */
sealed interface OutboxPlan {
    data class Insert(val op: OutboxEntity) : OutboxPlan
    data class Update(val op: OutboxEntity) : OutboxPlan
    data class Delete(val opId: String) : OutboxPlan
    data object Nothing : OutboxPlan
}

object OutboxRules {
    /**
     * A field changed from [current] to [new]. If a change to the same field is already pending,
     * keep its original base value and just move its target; if the target returns to the
     * laptop's value, the pending change disappears.
     */
    fun setField(existing: OutboxEntity?, current: String?, new: String?, make: (base: String?) -> OutboxEntity): OutboxPlan =
        when {
            existing == null && current == new -> OutboxPlan.Nothing
            existing == null -> OutboxPlan.Insert(make(current))
            existing.baseValue == new -> OutboxPlan.Delete(existing.opId)
            existing.newValue == new -> OutboxPlan.Nothing
            else -> OutboxPlan.Update(existing.copy(newValue = new))
        }

    /** Add/remove of a topic or tag link. The opposite pending op cancels out; a repeat does nothing. */
    fun link(existing: OutboxEntity?, op: String, make: () -> OutboxEntity): OutboxPlan =
        when {
            existing == null -> OutboxPlan.Insert(make())
            existing.op != op -> OutboxPlan.Delete(existing.opId)
            else -> OutboxPlan.Nothing
        }
}
