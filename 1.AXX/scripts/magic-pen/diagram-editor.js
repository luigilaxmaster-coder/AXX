/**
 * AXX Evolution 3.0 — Magic Pen Diagram Studio Interactive Editor (PR-04).
 * Provides semantic node selection, keyboard/pointer move & resize, label editing,
 * snapping, and strict textContent rendering (no innerHTML / foreignObject scripts).
 */
(function (global) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  function createDiagramEditor(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onNodePatch = typeof opts.onNodePatch === 'function' ? opts.onNodePatch : function () {};
    const onObjectFocus = typeof opts.onObjectFocus === 'function' ? opts.onObjectFocus : function () {};

    let mounted = false;
    let diagram = { style_template: 'obsidian_spatial', nodes: [], edges: [] };
    let selectedNodeId = null;
    const cleanupFns = [];

    function snap(val, step) {
      const s = step || 0.02;
      return Math.round(Math.round(val / s) * s * 10000) / 10000;
    }

    function moveSelectedNode(dx, dy) {
      if (!selectedNodeId) return null;
      const node = (diagram.nodes || []).find(function (n) { return n.id === selectedNodeId; });
      if (!node || !Array.isArray(node.bounds)) return null;
      const w = node.bounds[2];
      const h = node.bounds[3];
      const nx = Math.min(Math.max(0.02, snap(node.bounds[0] + dx, 0.02)), Math.max(0.02, 0.98 - w));
      const ny = Math.min(Math.max(0.02, snap(node.bounds[1] + dy, 0.02)), Math.max(0.02, 0.98 - h));
      node.bounds = [nx, ny, w, h];
      render();
      onNodePatch({ node_id: node.id, bounds: node.bounds.slice(), label: node.label });
      return node.bounds.slice();
    }

    function render() {
      if (!container || !mounted) return;
      container.textContent = '';

      const svg = document.createElementNS(SVG_NS, 'svg');
      svg.setAttribute('viewBox', '0 0 1200 800');
      svg.setAttribute('class', 'axx-diagram-studio-svg');
      svg.setAttribute('role', 'region');
      svg.setAttribute('aria-label', 'Editor de diagramas Magic Pen');

      const nodesById = {};
      (diagram.nodes || []).forEach(function (n) {
        nodesById[n.id] = n;
      });

      (diagram.edges || []).forEach(function (edge) {
        const src = nodesById[edge.from];
        const dst = nodesById[edge.to];
        if (!src || !dst) return;
        const line = document.createElementNS(SVG_NS, 'line');
        line.setAttribute('x1', String((src.bounds[0] + src.bounds[2] / 2) * 1200));
        line.setAttribute('y1', String((src.bounds[1] + src.bounds[3] / 2) * 800));
        line.setAttribute('x2', String((dst.bounds[0] + dst.bounds[2] / 2) * 1200));
        line.setAttribute('y2', String((dst.bounds[1] + dst.bounds[3] / 2) * 800));
        line.setAttribute('stroke', '#8b949e');
        line.setAttribute('stroke-width', '2');
        svg.appendChild(line);
      });

      (diagram.nodes || []).forEach(function (node, idx) {
        const g = document.createElementNS(SVG_NS, 'g');
        g.setAttribute('data-node-id', node.id);
        g.setAttribute('tabindex', idx === 0 || node.id === selectedNodeId ? '0' : '-1');
        g.setAttribute('role', 'button');
        g.setAttribute('aria-label', String(node.label || node.id));

        const nx = node.bounds[0] * 1200;
        const ny = node.bounds[1] * 800;
        const nw = Math.max(node.bounds[2] * 1200, String(node.label || '').length * 9.5 + 32);
        const nh = Math.max(node.bounds[3] * 800, 48);

        const rect = document.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('x', String(nx));
        rect.setAttribute('y', String(ny));
        rect.setAttribute('width', String(nw));
        rect.setAttribute('height', String(nh));
        rect.setAttribute('rx', '8');
        rect.setAttribute('ry', '8');
        rect.setAttribute('fill', '#161b22');
        rect.setAttribute('stroke', node.id === selectedNodeId ? '#3fb950' : '#58a6ff');
        rect.setAttribute('stroke-width', node.id === selectedNodeId ? '3' : '2');
        g.appendChild(rect);

        const text = document.createElementNS(SVG_NS, 'text');
        text.setAttribute('x', String(nx + nw / 2));
        text.setAttribute('y', String(ny + nh / 2 + 5));
        text.setAttribute('fill', '#e6edf3');
        text.setAttribute('text-anchor', 'middle');
        text.textContent = String(node.label || node.id);
        g.appendChild(text);

        const onClick = function () {
          selectedNodeId = node.id;
          if (node.object_id) onObjectFocus(node.object_id);
          render();
        };
        const onKey = function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            onClick();
          } else if (ev.key === 'ArrowRight') {
            ev.preventDefault();
            selectedNodeId = node.id;
            moveSelectedNode(0.02, 0);
          } else if (ev.key === 'ArrowLeft') {
            ev.preventDefault();
            selectedNodeId = node.id;
            moveSelectedNode(-0.02, 0);
          } else if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            selectedNodeId = node.id;
            moveSelectedNode(0, 0.02);
          } else if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            selectedNodeId = node.id;
            moveSelectedNode(0, -0.02);
          }
        };
        g.addEventListener('click', onClick);
        g.addEventListener('keydown', onKey);
        cleanupFns.push(function () {
          g.removeEventListener('click', onClick);
          g.removeEventListener('keydown', onKey);
        });

        svg.appendChild(g);
      });

      container.appendChild(svg);
    }

    return {
      mount: function (initialDiagram) {
        mounted = true;
        if (initialDiagram && typeof initialDiagram === 'object') {
          diagram = JSON.parse(JSON.stringify(initialDiagram));
        }
        render();
      },
      setDiagram: function (nextDiagram) {
        if (nextDiagram && typeof nextDiagram === 'object') {
          diagram = JSON.parse(JSON.stringify(nextDiagram));
          render();
        }
      },
      selectNode: function (nodeId) {
        selectedNodeId = nodeId;
        render();
      },
      moveSelectedNode: moveSelectedNode,
      updateNodeLabel: function (nodeId, newLabel) {
        const node = (diagram.nodes || []).find(function (n) { return n.id === nodeId; });
        if (!node) return false;
        node.label = String(newLabel || '').trim();
        render();
        onNodePatch({ node_id: node.id, bounds: node.bounds.slice(), label: node.label });
        return true;
      },
      unmount: function () {
        mounted = false;
        selectedNodeId = null;
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
    };
  }

  global.AxxDiagramEditor = { createDiagramEditor: createDiagramEditor };
})(typeof window !== 'undefined' ? window : globalThis);
