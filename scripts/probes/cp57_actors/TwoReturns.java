package probe;

import java.util.concurrent.CompletionStage;
import org.apache.pekko.actor.typed.javadsl.ActorContext;

/** A mapper lambda whose body has two `return`s (the ternary in the fixture compiles to one). */
public final class TwoReturns {
  public interface Command {}

  public record Done(String body) implements Command {}

  public record Failed(Throwable cause) implements Command {}

  static void run(ActorContext<Command> context, CompletionStage<String> stage) {
    context.pipeToSelf(
        stage,
        (body, ex) -> {
          if (ex != null) {
            return new Failed(ex);
          }
          return new Done(body);
        });
  }
}
