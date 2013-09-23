(defn trigger [context]
  (and
    (= context.prefix.nick "joar")
    context.params.trailing
    (= (slice context.params.trailing 0 5) "!join")))

(defn act [context]
  (, "JOIN" (slice context.params.trailing 6)))
