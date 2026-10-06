document.addEventListener("DOMContentLoaded", function () {
  const messages = document.getElementById("messages");
  if (messages) messages.scrollTop = messages.scrollHeight;

  const adminSearch = document.getElementById("adminSearch");
  if (adminSearch) {
    adminSearch.addEventListener("input", function () {
      const q = this.value.toLowerCase();
      document.querySelectorAll("#usersTable tbody tr").forEach(function (row) {
        row.style.display = row.innerText.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  setTimeout(function () {
    document.querySelectorAll(".toast").forEach(function (el) { el.remove(); });
  }, 4500);
});