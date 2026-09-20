package cp23

class Shapes {
    fun greet(name: String = "x", loud: Boolean = false): String = if (loud) name.uppercase() else name
    fun callsGreetWithDefaults(): String = greet()                  // mask 0b11
    fun callsGreetPartially(): String = greet("y")                  // mask 0b10
    fun wide(
        p0: Int = 0, p1: Int = 0, p2: Int = 0, p3: Int = 0, p4: Int = 0, p5: Int = 0, p6: Int = 0, p7: Int = 0,
        p8: Int = 0, p9: Int = 0, p10: Int = 0, p11: Int = 0, p12: Int = 0, p13: Int = 0, p14: Int = 0, p15: Int = 0,
        p16: Int = 0, p17: Int = 0, p18: Int = 0, p19: Int = 0, p20: Int = 0, p21: Int = 0, p22: Int = 0, p23: Int = 0,
        p24: Int = 0, p25: Int = 0, p26: Int = 0, p27: Int = 0, p28: Int = 0, p29: Int = 0, p30: Int = 0, p31: Int = 0,
        p32: Int = 0,
    ): Int = p32
    fun callsWide(): Int = wide(p32 = 1)                            // two masks: 0xFFFFFFFF, 0b0
    fun plain(): (String) -> Int = { it.length }
    fun suspended(): suspend (String) -> Int = { it.length }
    fun capturing(prefix: String): (String) -> String = { prefix + it }
}
object Statics { @JvmStatic fun js(a: String, b: Int = 0): String = a + b; fun callsJs() = js("a") }
