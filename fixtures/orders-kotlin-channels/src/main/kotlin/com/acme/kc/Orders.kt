package com.acme.kc

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.consumeEach
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.channels.SendChannel
import kotlinx.coroutines.channels.produce

data class Order(val id: Long)

/** A channel held in a field: a producer coroutine sends, a consumer loops over it. A second
 *  channel of the same type, `audit`, has its own send and receive. */
class Pipeline {
    private val orders = Channel<Order>(Channel.UNLIMITED)
    private val audit = Channel<Order>()

    fun start(scope: CoroutineScope) {
        scope.launch { orders.send(Order(1)) }
        scope.launch { for (o in orders) handle(o) }
    }

    suspend fun submit(order: Order) {
        orders.send(order)
    }

    suspend fun later(order: Order) {
        delay(1)
        orders.send(order)
    }

    fun trySubmit(order: Order): Boolean = orders.trySend(order).isSuccess

    suspend fun drain() {
        for (o in orders) handle(o)
    }

    suspend fun next(): Order = orders.receive()

    fun poll(): Order? = orders.tryReceive().getOrNull()

    suspend fun each() {
        orders.consumeEach { handle(it) }
    }

    suspend fun record(order: Order) {
        audit.send(order)
    }

    suspend fun auditNext(): Order = audit.receive()

    suspend fun feed() {
        pump(audit, 2)
    }

    /** The channel is a parameter, needed across the first suspension and dead at the second:
     *  kotlinc 2.4 spills it into the continuation and nulls the slot out at the second. */
    private suspend fun pump(channel: SendChannel<Order>, count: Int) {
        delay(1)
        channel.send(Order(count.toLong()))
        delay(2)
        println(count)
    }

    private fun handle(order: Order) {
        println(order)
    }
}

/** A channel handed in through a data class's constructor and read through its property, made
 *  by the `Channel(capacity)` factory (examples/playport's `WsClient`). */
data class Client(val channel: Channel<String>)

class Hub {
    private val clients = mutableSetOf<Client>()

    fun connect(scope: CoroutineScope) {
        val client = Client(Channel(capacity = 16))
        clients += client
        scope.launch {
            for (frame in client.channel) println(frame)
        }
    }

    fun broadcast(text: String) {
        for (client in clients) client.channel.trySend(text)
    }
}

/** A channel from outside the module: nothing here makes it, so which object it is is not read. */
class Relay(private val inbox: Channel<Order>) {
    suspend fun forward(order: Order) {
        inbox.send(order)
    }
}

/** A channel in a local, captured by the coroutine that sends on it and looped over by the
 *  block that made it: kotlinc keeps it in the launched lambda's own `$jobs` field. */
class Workers {
    suspend fun run() = coroutineScope {
        val jobs = Channel<Order>()
        launch { jobs.send(Order(2)) }
        for (job in jobs) println(job)
    }
}

/** A producer coroutine: `produce { send(x) }` sends on the `ProducerScope` the library hands
 *  its block, and the caller loops over the channel the library returns. Neither object is made
 *  by a call the walk can pair, so the send is a stop that says so. */
class Numbers {
    fun CoroutineScope.numbers() = produce { send(Order(3)) }

    suspend fun sum(scope: CoroutineScope) {
        for (n in scope.numbers()) println(n)
    }
}

/** Near miss for `kotlinx-channels`: the module's own type with a channel's method names and
 *  shapes (a suspending `send`, a `receive`, a `for` loop over its `iterator()`), not a channel. */
class Outbox {
    private val held = ArrayDeque<Order>()

    suspend fun send(order: Order) {
        held.addLast(order)
    }

    suspend fun receive(): Order = held.removeFirst()

    operator fun iterator(): Iterator<Order> = held.iterator()
}

class OutboxUser(private val outbox: Outbox) {
    suspend fun push(order: Order) {
        outbox.send(order)
    }

    suspend fun pull(): Order = outbox.receive()

    fun all() {
        for (order in outbox) println(order)
    }
}
