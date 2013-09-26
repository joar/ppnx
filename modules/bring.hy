(defn trigger [context]
  (and
    context.params.trailing
    (= (slice context.params.trailing 0 6) "!bring")))

(defn act [context]
  (setv subject (slice context.params.trailing 7))
  (.format "\x01ACTION brings {0}\x01" subject))
