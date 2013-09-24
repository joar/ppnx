(import [re])
(import [requests [get :as http-get]])

(setv issue-regex (re.compile "github\.com/(([^/]+)/([^/]+)/issues/(\d+))"))

(defn trigger [context]
  (and
    context.params.trailing
    (get-issue-url context.params.trailing)))

(defn get-issue-url [line]
  (setv result (.search issue-regex line))
  (if result
    (result.group 1)))

(defn act [context]
  (let
    [[
      issue-data
      (.json (http-get (.format
          "https://api.github.com/repos/{0}"
          (get-issue-url context.params.trailing))))
    ]]
    (.format
      "({0}) #{1}: {2}"
      (get issue-data "state")
      (get issue-data "number")
      (get issue-data "title"))))
