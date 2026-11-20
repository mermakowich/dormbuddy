const profile = document.querySelector("[data-profile]");

if (profile) {
  const mode = profile.elements.mode;
  const university = profile.elements.university_id;
  const dormitory = profile.elements.dormitory_id;

  function updateDormitories() {
    for (const group of dormitory.querySelectorAll("optgroup")) {
      const available = group.dataset.university === university.value;
      group.hidden = !available;
      group.disabled = !available;
    }
    const selectedGroup = dormitory.selectedOptions[0]?.closest("optgroup");
    if (selectedGroup?.disabled) dormitory.value = "";
  }

  function updateMode() {
    for (const panel of profile.querySelectorAll("[data-mode]")) {
      panel.hidden = panel.dataset.mode !== mode.value;
      for (const control of panel.querySelectorAll("input, select")) {
        control.disabled = panel.hidden;
      }
    }
    university.required = mode.value === "dorm";
    dormitory.required = mode.value === "dorm";
    updateDormitories();
  }

  mode.addEventListener("change", updateMode);
  university.addEventListener("change", updateDormitories);
  updateMode();
}

const buddyQuestion = document.querySelector("#question");

if (buddyQuestion) {
  for (const prompt of document.querySelectorAll("[data-prompt]")) {
    prompt.addEventListener("click", () => {
      buddyQuestion.value = prompt.textContent.trim();
      buddyQuestion.focus();
    });
  }
}

for (const form of document.querySelectorAll("[data-wait]")) {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    button.textContent = form.dataset.wait;
    form.setAttribute("aria-busy", "true");
  });
}
