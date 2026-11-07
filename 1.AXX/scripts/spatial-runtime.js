/**
 * Axx Live Spatial Runtime
 * Canvas-First Desktop Intelligence: 2D Overlay Renderer + Procedural 3D Viewer
 */
(() => {
    'use strict';
    const A = window.Axx = window.Axx || {};

    class SpatialRuntime {
        constructor() {
            this.activePlan = null;
            this.container3D = null;
            this.scene3D = null;
            this.explodedRatio = 0.0;
        }

        /**
         * Render 2D Vector annotations onto the Magic Pen canvas context.
         * @param {CanvasRenderingContext2D} ctx 
         * @param {object} plan SpatialPresentationPlan
         * @param {object} selection Bounds of current selection [x0, y0, x1, y1]
         */
        renderOverlay(ctx, plan, selection) {
            if (!ctx || !plan || !plan.annotations_2d || !plan.annotations_2d.length) return;
            const bounds = selection?.bounds || [0, 0, ctx.canvas.width, ctx.canvas.height];
            const [bx0, by0, bx1, by1] = bounds;
            const bw = Math.max(1, bx1 - bx0);
            const bh = Math.max(1, by1 - by0);

            ctx.save();
            const centers = [];

            // Draw diagram connections if mode is diagram_2d
            if (plan.mode === 'diagram_2d' && plan.annotations_2d.length > 1) {
                ctx.save();
                ctx.strokeStyle = '#38bdf888';
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 6]);
                for (let i = 0; i < plan.annotations_2d.length - 1; i++) {
                    const [ay0, ax0, ay1, ax1] = plan.annotations_2d[i].target_box_normalized || [0,0,1,1];
                    const [by0, bx0_n, by1, bx1_n] = plan.annotations_2d[i+1].target_box_normalized || [0,0,1,1];
                    const acx = bx0 + ((ax0 + ax1) / 2) * bw;
                    const acy = by0 + ((ay0 + ay1) / 2) * bh;
                    const bcx = bx0 + ((bx0_n + bx1_n) / 2) * bw;
                    const bcy = by0 + ((by0 + by1) / 2) * bh;

                    ctx.beginPath();
                    ctx.moveTo(acx, acy);
                    ctx.lineTo(bcx, bcy);
                    ctx.stroke();

                    // Step sequence badge
                    const midX = (acx + bcx) / 2;
                    const midY = (acy + bcy) / 2;
                    ctx.fillStyle = '#0284c7';
                    ctx.beginPath();
                    ctx.arc(midX, midY, 9, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.fillStyle = '#ffffff';
                    ctx.font = 'bold 10px system-ui';
                    ctx.fillText(String(i + 1), midX - 3, midY + 4);
                }
                ctx.restore();
            }

            for (const ann of plan.annotations_2d) {
                const [ymin, xmin, ymax, xmax] = ann.target_box_normalized || [0, 0, 1, 1];
                const x0 = bx0 + xmin * bw;
                const y0 = by0 + ymin * bh;
                const x1 = bx0 + xmax * bw;
                const y1 = by0 + ymax * bh;
                const w = Math.max(4, x1 - x0);
                const h = Math.max(4, y1 - y0);
                const color = ann.color || '#38bdf8';
                const cx = x0 + w / 2;
                const cy = y0 + h / 2;

                if (ann.type === 'arrow') {
                    // Precision pointing arrow
                    const arrowTailX = Math.max(8, x0 - 36);
                    const arrowTailY = Math.max(8, y0 - 36);

                    ctx.strokeStyle = color;
                    ctx.lineWidth = 3;
                    ctx.fillStyle = color;
                    ctx.setLineDash([]);

                    // Arrow shaft
                    ctx.beginPath();
                    ctx.moveTo(arrowTailX, arrowTailY);
                    ctx.lineTo(cx, cy);
                    ctx.stroke();

                    // Arrowhead at target point (cx, cy)
                    const angle = Math.atan2(cy - arrowTailY, cx - arrowTailX);
                    const headLen = 12;
                    ctx.beginPath();
                    ctx.moveTo(cx, cy);
                    ctx.lineTo(cx - headLen * Math.cos(angle - Math.PI / 6), cy - headLen * Math.sin(angle - Math.PI / 6));
                    ctx.lineTo(cx - headLen * Math.cos(angle + Math.PI / 6), cy - headLen * Math.sin(angle + Math.PI / 6));
                    ctx.closePath();
                    ctx.fill();

                    // Target ring
                    ctx.beginPath();
                    ctx.arc(cx, cy, 5, 0, Math.PI * 2);
                    ctx.stroke();
                } else if (ann.type === 'spotlight') {
                    // Spotlight elliptical radial glow
                    const r = Math.max(w, h) / 1.4;
                    const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, r);
                    grad.addColorStop(0, color + '66');
                    grad.addColorStop(0.7, color + '22');
                    grad.addColorStop(1, 'transparent');
                    ctx.fillStyle = grad;
                    ctx.beginPath();
                    ctx.arc(cx, cy, r, 0, Math.PI * 2);
                    ctx.fill();

                    ctx.strokeStyle = color;
                    ctx.lineWidth = 2;
                    ctx.stroke();
                } else {
                    // Box highlight with glowing stroke
                    ctx.fillStyle = color + '18';
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 2.5;
                    ctx.setLineDash([]);
                    ctx.beginPath();
                    if (ctx.roundRect) {
                        ctx.roundRect(x0, y0, w, h, 6);
                    } else {
                        ctx.rect(x0, y0, w, h);
                    }
                    ctx.fill();
                    ctx.stroke();
                }

                // Pill label
                if (ann.label) {
                    ctx.font = '600 13px system-ui, sans-serif';
                    const textWidth = ctx.measureText(ann.label).width;
                    const pillW = textWidth + 14;
                    const pillH = 22;
                    const pillX = Math.max(4, Math.min(ctx.canvas.width - pillW - 4, x0));
                    const pillY = Math.max(24, y0 - pillH - 4);

                    ctx.fillStyle = '#0f172ae6';
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    if (ctx.roundRect) {
                        ctx.roundRect(pillX, pillY, pillW, pillH, 4);
                    } else {
                        ctx.rect(pillX, pillY, pillW, pillH);
                    }
                    ctx.fill();
                    ctx.stroke();

                    ctx.fillStyle = '#f8fafc';
                    ctx.fillText(ann.label, pillX + 7, pillY + 15);
                }
            }
            ctx.restore();
        }

        /**
         * Mount a lightweight interactive 3D spatial card for GPT-6.1 Sol Fast scenes.
         * @param {HTMLElement} parent
         * @param {object} plan SpatialPresentationPlan
         */
        show3DCard(parent, plan) {
            this.dismiss3DCard();
            if (!plan?.scene_3d?.root_primitives || !parent) return;

            const card = document.createElement('div');
            card.id = 'axx-spatial-3d-card';
            card.className = 'spatial-3d-card';
            card.innerHTML = `
                <div class="spatial-card-header">
                    <span class="spatial-card-title">Vista 3D Espacial · GPT-6.1 Sol Fast</span>
                    <button id="spatial-card-close" title="Cerrar vista 3D">✕</button>
                </div>
                <div class="spatial-viewport-container">
                    <canvas id="spatial-3d-canvas" width="380" height="260"></canvas>
                </div>
                <div class="spatial-controls-bar">
                    <label>Exploded View: <input id="spatial-explode-slider" type="range" min="0" max="100" value="0"></label>
                    <span id="spatial-part-name" class="spatial-part-badge">Rotar: Arrastrar | Zoom: Rueda</span>
                </div>
            `;

            Object.assign(card.style, {
                position: 'fixed',
                bottom: '24px',
                right: '24px',
                width: '400px',
                background: '#0a0f1df2',
                border: '1px solid #38bdf888',
                borderRadius: '12px',
                boxShadow: '0 12px 36px #000a, 0 0 16px #38bdf833',
                color: '#e2e8f0',
                fontFamily: 'system-ui, sans-serif',
                zIndex: '999999',
                backdropFilter: 'blur(12px)',
                padding: '10px'
            });

            parent.appendChild(card);
            this.container3D = card;

            const closeBtn = card.querySelector('#spatial-card-close');
            if (closeBtn) closeBtn.onclick = () => this.dismiss3DCard();

            const slider = card.querySelector('#spatial-explode-slider');
            if (slider) {
                slider.oninput = (e) => {
                    this.explodedRatio = Number(e.target.value) / 100.0;
                    this.render3DPrimitives();
                };
            }

            this.init3DRenderer(card.querySelector('#spatial-3d-canvas'), plan.scene_3d);
        }

        init3DRenderer(canvas, sceneData) {
            if (!canvas || !sceneData) return;
            this.canvas3D = canvas;
            this.sceneData = sceneData;
            this.rotX = 0.35;
            this.rotY = 0.65;
            this.zoom = 1.0;
            this.isDragging = false;
            this.lastMouse = { x: 0, y: 0 };

            canvas.onpointerdown = (e) => {
                this.isDragging = true;
                this.lastMouse = { x: e.clientX, y: e.clientY };
                canvas.setPointerCapture(e.pointerId);
            };

            canvas.onpointermove = (e) => {
                if (!this.isDragging) return;
                const dx = e.clientX - this.lastMouse.x;
                const dy = e.clientY - this.lastMouse.y;
                this.rotY += dx * 0.015;
                this.rotX += dy * 0.015;
                this.lastMouse = { x: e.clientX, y: e.clientY };
                this.render3DPrimitives();
            };

            canvas.onpointerup = (e) => {
                this.isDragging = false;
                try { canvas.releasePointerCapture(e.pointerId); } catch {}
            };

            canvas.onwheel = (e) => {
                e.preventDefault();
                this.zoom = Math.max(0.4, Math.min(3.0, this.zoom - e.deltaY * 0.0015));
                this.render3DPrimitives();
            };

            this.render3DPrimitives();
        }

        render3DPrimitives() {
            const canvas = this.canvas3D;
            if (!canvas || !this.sceneData) return;
            const ctx = canvas.getContext('2d');
            const w = canvas.width, h = canvas.height;
            ctx.clearRect(0, 0, w, h);

            // Subtle 3D grid floor
            ctx.save();
            ctx.strokeStyle = '#1e293b';
            ctx.lineWidth = 1;
            for (let i = -80; i <= 80; i += 20) {
                ctx.beginPath();
                ctx.moveTo(w / 2 + i * this.zoom, h / 2 + 60 * this.zoom);
                ctx.lineTo(w / 2 + (i + 40) * this.zoom, h / 2 + 100 * this.zoom);
                ctx.stroke();
            }
            ctx.restore();

            const cx = w / 2;
            const cy = h / 2;
            const scale = 24 * this.zoom;
            const t = this.explodedRatio;

            // Sort primitives back-to-front (simple painter's algorithm)
            const primitives = (this.sceneData.root_primitives || []).map((prim) => {
                const basePos = prim.position || [0, 0, 0];
                const offset = prim.exploded_offset || [0, 0, 0];
                const px = basePos[0] + offset[0] * t;
                const py = basePos[1] + offset[1] * t;
                const pz = basePos[2] + offset[2] * t;

                // 3D rotation projection (Euler yaw/pitch)
                const cosY = Math.cos(this.rotY), sinY = Math.sin(this.rotY);
                const cosX = Math.cos(this.rotX), sinX = Math.sin(this.rotX);

                const x1 = px * cosY - pz * sinY;
                const z1 = px * sinY + pz * cosY;
                const y1 = py * cosX - z1 * sinX;
                const z2 = py * sinX + z1 * cosX;

                return { prim, screenX: cx + x1 * scale, screenY: cy - y1 * scale, depth: z2 };
            });

            primitives.sort((a, b) => a.depth - b.depth);

            for (const item of primitives) {
                const { prim, screenX, screenY } = item;
                const [dimW, dimH, dimD] = prim.dimensions || [1, 1, 1];
                const color = prim.color || '#38bdf8';
                const pw = Math.max(6, dimW * scale);
                const ph = Math.max(6, dimH * scale);

                ctx.save();
                ctx.translate(screenX, screenY);

                if (prim.type === 'cylinder' || prim.type === 'shaft' || prim.type === 'piston') {
                    // 3D Cylinder / Piston procedural isometric render
                    ctx.fillStyle = color + 'cc';
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    ctx.ellipse(0, -ph / 2, pw / 2, pw / 4, 0, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();

                    ctx.beginPath();
                    ctx.rect(-pw / 2, -ph / 2, pw, ph);
                    ctx.fill();
                    ctx.stroke();

                    ctx.beginPath();
                    ctx.ellipse(0, ph / 2, pw / 2, pw / 4, 0, 0, Math.PI * 2);
                    ctx.fillStyle = color + 'ee';
                    ctx.fill();
                    ctx.stroke();
                } else if (prim.type === 'sphere') {
                    const r = Math.max(6, (dimW * scale) / 2);
                    const grad = ctx.createRadialGradient(-r * 0.3, -r * 0.3, r * 0.1, 0, 0, r);
                    grad.addColorStop(0, '#ffffff');
                    grad.addColorStop(0.3, color);
                    grad.addColorStop(1, '#020617');
                    ctx.fillStyle = grad;
                    ctx.beginPath();
                    ctx.arc(0, 0, r, 0, Math.PI * 2);
                    ctx.fill();
                } else {
                    // Box / PCB / Chip procedural cube
                    ctx.fillStyle = color + 'bb';
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    ctx.rect(-pw / 2, -ph / 2, pw, ph);
                    ctx.fill();
                    ctx.stroke();
                }

                // Primitive tag
                ctx.fillStyle = '#ffffff';
                ctx.font = '10px system-ui, sans-serif';
                ctx.fillText(prim.id, -pw / 2, ph / 2 + 12);
                ctx.restore();
            }
        }

        dismiss3DCard() {
            if (this.container3D) {
                this.container3D.remove();
                this.container3D = null;
                this.canvas3D = null;
                this.sceneData = null;
            }
        }
    }

    A.spatialRuntime = new SpatialRuntime();
})();
