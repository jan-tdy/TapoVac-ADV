# Changelog

This page loads the project's [GitHub Releases](https://github.com/jan-tdy/TapoVac-ADV/releases)
live, so it can't drift out of date the way a copy pasted into this page
would. If your browser blocks the request (ad blocker, offline, GitHub's
API rate limit), use the link above instead.

<div id="changelog-list">Loading releases from GitHub…</div>

<script>
(function () {
  var el = document.getElementById("changelog-list");

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Minimal, safe formatting for GitHub-flavored release notes: the input is
  // escaped first, so this only ever adds tags around text that was already
  // there - it can't introduce new markup from the release body itself.
  function formatBody(raw) {
    var escaped = escapeHtml(raw);
    escaped = escaped.replace(/\r\n/g, "\n");
    escaped = escaped.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    escaped = escaped.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    escaped = escaped.replace(
      /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2">$1</a>'
    );
    escaped = escaped.replace(
      /(^|[\s(])(https?:\/\/[^\s)]+)/g,
      '$1<a href="$2">$2</a>'
    );
    escaped = escaped.split("\n").map(function (line) {
      return line.replace(/^\s*[-*]\s+/, "");
    });
    return escaped
      .map(function (line) { return line.trim() ? "<li>" + line + "</li>" : ""; })
      .join("");
  }

  fetch("https://api.github.com/repos/jan-tdy/TapoVac-ADV/releases?per_page=30")
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (releases) {
      if (!releases.length) {
        el.textContent = "No releases yet.";
        return;
      }
      var html = "";
      releases.forEach(function (rel) {
        var date = new Date(rel.published_at).toLocaleDateString(undefined, {
          year: "numeric", month: "long", day: "numeric",
        });
        var title = escapeHtml(rel.name || rel.tag_name);
        var badge = rel.prerelease ? ' <em>(pre-release)</em>' : "";
        html +=
          '<h3 id="' + escapeHtml(rel.tag_name) + '">' +
          '<a href="' + rel.html_url + '">' + title + "</a>" + badge +
          "</h3>" +
          '<p><small>' + date + "</small></p>" +
          "<ul>" + formatBody(rel.body || "(no release notes)") + "</ul>";
      });
      el.innerHTML = html;
    })
    .catch(function (err) {
      el.innerHTML =
        "<p>Couldn't load releases from GitHub's API (" + escapeHtml(err.message) +
        '). See the <a href="https://github.com/jan-tdy/TapoVac-ADV/releases">releases page</a> directly.</p>';
    });
})();
</script>
