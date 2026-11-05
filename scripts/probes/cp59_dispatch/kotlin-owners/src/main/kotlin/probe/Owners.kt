package probe

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ProducerScope
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.channels.SendChannel
import kotlinx.coroutines.channels.consumeEach
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

// Each call the catalogs declare (and the near forms beside them), through each owner type a
// Kotlin source can hold the object as. One function per owner, so each call's owner is the
// one its function names.

suspend fun channel(c: Channel<Any>, v: Any) {
    c.send(v); c.trySend(v)
    c.receive(); c.tryReceive(); c.receiveCatching()
    for (x in c) println(x)
    c.consumeEach { println(it) }
}

suspend fun sendChannel(c: SendChannel<Any>, v: Any) {
    c.send(v); c.trySend(v)
}

suspend fun producerScope(c: ProducerScope<Any>, v: Any) {
    c.send(v); c.trySend(v)
}

suspend fun receiveChannel(c: ReceiveChannel<Any>) {
    c.receive(); c.tryReceive(); c.receiveCatching()
    for (x in c) println(x)
    c.consumeEach { println(it) }
}

suspend fun mutableSharedFlow(f: MutableSharedFlow<Any>, v: Any) {
    f.emit(v); f.tryEmit(v)
    f.collect { println(it) }
}

suspend fun mutableStateFlow(f: MutableStateFlow<Any>, v: Any) {
    f.value = v; f.emit(v); f.tryEmit(v); f.compareAndSet(v, v)
    f.update { it }
    f.collect { println(it) }
}

suspend fun sharedFlow(f: SharedFlow<Any>) {
    f.collect { println(it) }
}

suspend fun stateFlow(f: StateFlow<Any>) {
    f.collect { println(it) }
}

suspend fun flow(f: Flow<Any>) {
    f.collect { println(it) }
}
