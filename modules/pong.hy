(defn trigger [context]
  (= context.command "PING"))

(defn act [context]
  (, "PONG"))
