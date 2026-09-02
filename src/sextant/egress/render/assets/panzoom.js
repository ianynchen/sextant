// panzoom.js — Sextant's own pan/zoom for a rendered document's diagrams
// (2K design §6b). Not a vendored library: wheel zoom, drag pan, and
// +/-/reset controls, applied as a CSS transform on the element mermaid
// rendered its SVG into. One instance per ".diagram" container, so a
// document with many diagrams keeps them independent.
//
// Wheel convention: a PLAIN wheel over a diagram scrolls the page, exactly
// as it would anywhere else — the page is usually taller than one screen,
// and a diagram that ate every scroll gesture under the cursor would break
// reading the document around it. Only ctrl/cmd+wheel zooms, and only that
// combination calls preventDefault: the "maps" convention (Google Maps and
// friends). It is also exactly right for a trackpad: a pinch gesture is
// delivered to the browser as a wheel event with `ctrlKey` set, so
// "ctrl+wheel zooms" already covers pinch-to-zoom with no separate touch
// handling.
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

    // Zoom by `factor`, keeping the point at VIEWPORT coordinates (px, py)
    // visually fixed — standard "zoom at the pointer" math: the translate is
    // corrected by the ratio the scale actually changed by, which is not
    // necessarily `factor` itself once `clamp` has capped it.
    function zoomAt(px, py, factor) {
      var nextScale = clamp(scale * factor);
      var ratio = nextScale / scale;
      x = px - (px - x) * ratio;
      y = py - (py - y) * ratio;
      scale = nextScale;
      apply();
    }

    // The +/- buttons have no cursor position of their own, so they anchor
    // at the viewport's center instead.
    function zoomAtCenter(factor) {
      var rect = viewport.getBoundingClientRect();
      zoomAt(rect.width / 2, rect.height / 2, factor);
    }

    viewport.addEventListener(
      "wheel",
      function (event) {
        if (!event.ctrlKey && !event.metaKey) {
          return; // plain wheel: let the page scroll, untouched
        }
        event.preventDefault();
        var rect = viewport.getBoundingClientRect();
        zoomAt(
          event.clientX - rect.left,
          event.clientY - rect.top,
          event.deltaY < 0 ? 1.1 : 0.9,
        );
      },
      { passive: false },
    );

    viewport.addEventListener("mousedown", function (event) {
      // Without this, a drag starting over the rendered SVG's text nodes
      // starts a native text selection instead of a pan.
      event.preventDefault();
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
        zoomAtCenter(1.2);
      });
    }
    if (zoomOut) {
      zoomOut.addEventListener("click", function () {
        zoomAtCenter(0.8);
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
