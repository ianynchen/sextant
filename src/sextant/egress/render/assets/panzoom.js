// panzoom.js — Sextant's own pan/zoom for a rendered document's diagrams
// (2K design §6b). Not a vendored library: wheel zoom, drag pan, and
// +/-/reset controls, applied as a CSS transform on the element mermaid
// rendered its SVG into. One instance per ".diagram" container, so a
// document with many diagrams keeps them independent.
(function () {
  "use strict";

  var MIN_SCALE = 0.2;
  var MAX_SCALE = 8;

  function clamp(scale) {
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
  }

  function setUpDiagram(container) {
    var viewport = container.querySelector(".diagram-viewport");
    var canvas = container.querySelector(".diagram-canvas");
    if (!viewport || !canvas) {
      return;
    }

    var scale = 1;
    var x = 0;
    var y = 0;
    var dragging = false;
    var lastX = 0;
    var lastY = 0;

    function apply() {
      canvas.style.transform =
        "translate(" + x + "px, " + y + "px) scale(" + scale + ")";
    }

    function reset() {
      scale = 1;
      x = 0;
      y = 0;
      apply();
    }

    viewport.addEventListener(
      "wheel",
      function (event) {
        event.preventDefault();
        scale = clamp(scale * (event.deltaY < 0 ? 1.1 : 0.9));
        apply();
      },
      { passive: false },
    );

    viewport.addEventListener("mousedown", function (event) {
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      viewport.classList.add("dragging");
    });
    window.addEventListener("mousemove", function (event) {
      if (!dragging) {
        return;
      }
      x += event.clientX - lastX;
      y += event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      apply();
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
      viewport.classList.remove("dragging");
    });

    var zoomIn = container.querySelector(".diagram-zoom-in");
    var zoomOut = container.querySelector(".diagram-zoom-out");
    var resetButton = container.querySelector(".diagram-reset");
    if (zoomIn) {
      zoomIn.addEventListener("click", function () {
        scale = clamp(scale * 1.2);
        apply();
      });
    }
    if (zoomOut) {
      zoomOut.addEventListener("click", function () {
        scale = clamp(scale * 0.8);
        apply();
      });
    }
    if (resetButton) {
      resetButton.addEventListener("click", reset);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var containers = document.querySelectorAll(".diagram");
    for (var i = 0; i < containers.length; i++) {
      setUpDiagram(containers[i]);
    }
  });
})();
