(import [random])

(defn trigger [context]
  (if (is-not context.params.trailing None)
    (= (slice context.params.trailing 0 5) "!fate")))

(setv DICE_REPR {
  -1 "[-]"
  0  "[_]"
  1  "[+]"})

(defn act [context]
  (do
    (setv results
      (list-comp
        (random.randrange -1 2)
        (i (range 4))))
    (.format "{0} => {1}"
      (.join " "
        (list-comp
          (.get DICE_REPR i)
          (i results)))
      (sum results))))
