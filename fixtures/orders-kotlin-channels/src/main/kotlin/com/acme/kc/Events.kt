package com.acme.kc

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

data class Event(val name: String)

/** A shared flow with three collectors: every collector receives each event. Two collect in
 *  this class with lambdas that capture nothing; `Mailer` collects through the property, with a
 *  lambda that captures. */
class Bus {
    val events = MutableSharedFlow<Event>()

    suspend fun publish(event: Event) {
        events.emit(event)
    }

    fun tryPublish(event: Event): Boolean = events.tryEmit(event)

    suspend fun mail() {
        events.collect { event -> println("mail $event") }
    }

    suspend fun log() {
        events.collect { event -> println("log $event") }
    }
}

class Mailer(private val bus: Bus, private val prefix: String) {
    suspend fun run() {
        bus.events.collect { event -> println(prefix + event) }
    }
}

class App {
    val bus = Bus()
    val mailer = Mailer(bus, "to: ")
}

/** A state flow set through its `value` property, by `emit` and by `update { }`, collected once. */
class Status {
    private val state = MutableStateFlow("idle")

    fun open() {
        state.value = "open"
    }

    suspend fun close() {
        state.emit("closed")
    }

    fun touch() {
        state.update { "$it!" }
    }

    suspend fun watch() {
        state.collect { println(it) }
    }
}

/** Near miss for `kotlinx-flows`: a cold `flow { emit(x) }` emits to the collector of each
 *  `collect`, its own `FlowCollector` (an owner neither catalog declares), not to a shared object;
 *  and a module `collect` taking a lambda is not a flow's. */
class Ticker {
    fun ticks() = flow { emit(Event("tick")) }

    fun collect(handler: (Event) -> Unit) {
        handler(Event("local"))
    }

    fun local() {
        collect { println(it) }
    }
}
