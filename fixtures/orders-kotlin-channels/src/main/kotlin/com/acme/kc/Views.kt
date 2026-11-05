package com.acme.kc

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.consumeAsFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.single
import kotlinx.coroutines.flow.toList

/** The read-only view idiom: each flow is emitted on privately and exposed through
 *  `asSharedFlow()`, and collected through the view by another class. Two flows of one type, so
 *  an emit on one never reaches the other's view. */
class Feed {
    private val _items = MutableSharedFlow<Event>()
    val items = _items.asSharedFlow()
    private val _alerts = MutableSharedFlow<Event>()
    val alerts = _alerts.asSharedFlow()

    suspend fun push(event: Event) {
        _items.emit(event)
    }

    suspend fun alert(event: Event) {
        _alerts.emit(event)
    }
}

class FeedReader(private val feed: Feed) {
    suspend fun read() {
        feed.items.collect { println("item $it") }
    }

    suspend fun watchAlerts() {
        feed.alerts.collect { println("alert $it") }
    }
}

class FeedApp {
    val feed = Feed()
    val reader = FeedReader(feed)
}

/** A state flow set privately and collected through its `asStateFlow()` view. */
class Gauge {
    private val _level = MutableStateFlow(0)
    val level = _level.asStateFlow()

    fun set(value: Int) {
        _level.value = value
    }

    suspend fun show() {
        level.collect { println(it) }
    }
}

/** A channel read as a flow: `receiveAsFlow()` (several collectors share the values) and
 *  `consumeAsFlow()` (one collector). */
class Inbox {
    private val letters = Channel<Order>()

    suspend fun post(order: Order) {
        letters.send(order)
    }

    suspend fun stream() {
        letters.receiveAsFlow().collect { println(it) }
    }

    suspend fun drainAll() {
        letters.consumeAsFlow().collect { println(it) }
    }
}

/** Terminal receives: the first value, the first matching one, the only one, every one, and
 *  `collectLatest`, whose block handles each value. */
class Snapshot {
    private val latest = MutableSharedFlow<Event>(replay = 1)

    suspend fun update(event: Event) {
        latest.emit(event)
    }

    suspend fun current(): Event = latest.first()

    suspend fun matching(): Event? = latest.firstOrNull { it.name == "x" }

    suspend fun only(): Event = latest.single()

    suspend fun all(): List<Event> = latest.toList()

    suspend fun follow() {
        latest.collectLatest { println(it) }
    }
}
