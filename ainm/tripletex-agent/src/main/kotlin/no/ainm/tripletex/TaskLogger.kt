package no.ainm.tripletex

import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

object TaskLogger {
    private val logDir = File("logs").also { it.mkdirs() }
    private val logFile = File(logDir, "tripletex-log.txt")
    private val timeFormat = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    fun separator() {
        val ts = LocalDateTime.now().format(timeFormat)
        val line = "\n${"=".repeat(80)}\n=== NEW TASK at $ts ${"=".repeat(80 - 20 - ts.length)}\n${"=".repeat(80)}\n"
        System.out.print(line)
        System.out.flush()
        logFile.appendText(line)
    }

    fun log(msg: String) {
        System.out.println(msg)
        System.out.flush()
        logFile.appendText(msg + "\n")
    }
}
