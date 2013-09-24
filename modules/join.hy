(defn trigger [context]
  (and
    context.is_admin
    context.params.trailing
    (= (slice context.params.trailing 0 5) "!join")))

(defn act [context]
  (, "JOIN" (slice context.params.trailing 6)))
