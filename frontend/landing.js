/**
 * Lemma Landing Page Animation Engine
 */

document.addEventListener("DOMContentLoaded", () => {
    /* -------------------------------------------------------------
     * 1. Dynamic Typewriter Animation
     * ------------------------------------------------------------- */
    const typewriter = document.getElementById("typewriter");
    const words = ["analyze", "rewrite", "verify"];
    let wordIndex = 0;
    let charIndex = 0;
    let isDeleting = false;
    let typingSpeed = 100;

    function handleTypewriter() {
        const currentWord = words[wordIndex];

        if (isDeleting) {
            // Delete text
            typewriter.textContent = currentWord.substring(0, charIndex - 1);
            charIndex--;
            typingSpeed = 50; // faster deletion
        } else {
            // Type text
            typewriter.textContent = currentWord.substring(0, charIndex + 1);
            charIndex++;
            typingSpeed = 120; // standard typing
        }

        // Word completed typing
        if (!isDeleting && charIndex === currentWord.length) {
            isDeleting = true;
            typingSpeed = 2000; // pause before deleting
        } else if (isDeleting && charIndex === 0) {
            isDeleting = false;
            // Cycle to next word
            wordIndex = (wordIndex + 1) % words.length;
            typingSpeed = 500; // brief pause before next word
        }

        setTimeout(handleTypewriter, typingSpeed);
    }

    // Start typewriter
    setTimeout(handleTypewriter, 1000);


    /* -------------------------------------------------------------
     * 2. Interactive 3D Particle Sphere Canvas
     * ------------------------------------------------------------- */
    const canvas = document.getElementById("particle-canvas");
    const ctx = canvas.getContext("2d");

    let width, height;
    let sphereRadius = 160;
    let particles = [];
    const particleCount = 520;
    const goldenRatio = (1 + Math.sqrt(5)) / 2;

    // Rotation variables (idle velocities)
    let rotXVelocity = 0.002;
    let rotYVelocity = 0.003;
    let rotX = 0;
    let rotY = 0;

    // Interactive mouse trackers
    let mouse = { x: 0, y: 0, active: false, px: 0, py: 0 };

    // Animation States: "SPHERE", "BURST", "ROAM", "REFORM"
    let animationState = "SPHERE";
    let lastTime = performance.now();
    let stateTime = 0; // Accumulated time in the current state (in milliseconds)

    // Setup canvas size
    function resizeCanvas() {
        const clientWidth = window.innerWidth;
        const clientHeight = window.innerHeight;

        // Skip resizing if parent client size is reported as 0
        if (clientWidth === 0 || clientHeight === 0) return;

        width = canvas.width = clientWidth;
        height = canvas.height = clientHeight;

        // Scale sphere size based on screen width
        if (width < 600) {
            sphereRadius = 100;
        } else if (width < 1000) {
            sphereRadius = 130;
        } else {
            sphereRadius = 160;
        }
    }
    window.addEventListener("resize", resizeCanvas);

    // Generate coordinates using Fibonacci Sphere distribution
    function initParticles() {
        particles = [];
        for (let i = 0; i < particleCount; i++) {
            // y goes from 1 to -1
            const y = 1 - (i / (particleCount - 1)) * 2;
            const radiusAtY = Math.sqrt(1 - y * y);
            const theta = (2 * Math.PI * i) / goldenRatio;

            const x = Math.cos(theta) * radiusAtY;
            const z = Math.sin(theta) * radiusAtY;

            particles.push({
                ux: x,
                uy: y,
                uz: z,
                x: x * sphereRadius,
                y: y * sphereRadius,
                z: z * sphereRadius,
                vx: 0,
                vy: 0,
                vz: 0,
                colorShift: Math.random()
            });
        }
    }
    // Perform initial scaling & coordinate creation
    resizeCanvas();
    initParticles();


    // Mouse movement interaction listeners
    window.addEventListener("mousemove", (e) => {
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        if (mouseX >= 0 && mouseX <= rect.width && mouseY >= 0 && mouseY <= rect.height) {
            if (mouse.active) {
                // Dragging acceleration
                const dx = mouseX - mouse.px;
                const dy = mouseY - mouse.py;
                rotYVelocity -= dx * 0.0001;
                rotXVelocity -= dy * 0.0001;
            } else {
                // Gentle hover attraction
                const cx = width / 2;
                const cy = height / 2;
                const forceX = (mouseX - cx) / cx;
                const forceY = (mouseY - cy) / cy;
                rotYVelocity = 0.003 - forceX * 0.005;
                rotXVelocity = 0.002 - forceY * 0.005;
            }
            mouse.px = mouseX;
            mouse.py = mouseY;
            mouse.active = true;
        } else {
            mouse.active = false;
        }
    });

    // Touch Support for mobile
    window.addEventListener("touchmove", (e) => {
        if (e.touches.length > 0) {
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.touches[0].clientX - rect.left;
            const mouseY = e.touches[0].clientY - rect.top;
            if (mouseX >= 0 && mouseX <= rect.width && mouseY >= 0 && mouseY <= rect.height) {
                const dx = mouseX - mouse.px;
                const dy = mouseY - mouse.py;
                rotYVelocity -= dx * 0.0001;
                rotXVelocity -= dy * 0.0001;
                mouse.px = mouseX;
                mouse.py = mouseY;
            }
        }
    });

    // Main animation loop
    function animate() {
        ctx.clearRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;
        const fov = 350; // Camera field of view / focal distance

        // 1. Calculate time delta (dt) capped at 100ms to preserve tab transitions
        const now = performance.now();
        const dt = Math.min(now - lastTime, 100);
        lastTime = now;
        stateTime += dt;

        // 2. State machine transition timers (millisecond-based)
        if (animationState === "SPHERE") {
            if (stateTime > 12000) { // 12 seconds of standard sphere
                animationState = "BURST";
                stateTime = 0;

                // Fire radial velocities
                particles.forEach(p => {
                    const len = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z) || 1;
                    const force = 3.5 + Math.random() * 4.5; // Reduced burst force
                    p.vx = (p.x / len) * force + (Math.random() - 0.5) * 0.8;
                    p.vy = (p.y / len) * force + (Math.random() - 0.5) * 0.8;
                    p.vz = (p.z / len) * force + (Math.random() - 0.5) * 0.8;
                });
            }
        } else if (animationState === "BURST") {
            if (stateTime > 1500) { // 1.5 seconds of burst outward
                animationState = "ROAM";
                stateTime = 0;
            }
        } else if (animationState === "ROAM") {
            if (stateTime > 6000) { // 6 seconds of roaming
                animationState = "REFORM";
                stateTime = 0;
            }
        } else if (animationState === "REFORM") {
            if (stateTime > 3000) { // 3 seconds of grav-lerping back
                animationState = "SPHERE";
                stateTime = 0;
            }
        }

        // Slowly decay velocity back to idle speed
        rotXVelocity *= 0.98;
        rotYVelocity *= 0.98;

        // Maintain baseline speed
        if (Math.abs(rotXVelocity) < 0.001) rotXVelocity = 0.001 * Math.sign(rotXVelocity || 1);
        if (Math.abs(rotYVelocity) < 0.001) rotYVelocity = 0.0015 * Math.sign(rotYVelocity || 1);

        rotX += rotXVelocity;
        rotY += rotYVelocity;

        const cosX = Math.cos(rotX);
        const sinX = Math.sin(rotX);
        const cosY = Math.cos(rotY);
        const sinY = Math.sin(rotY);

        // Precompute projected 2D coordinates for rendering lines and points
        const projected = [];

        for (let i = 0; i < particles.length; i++) {
            const p = particles[i];

            // 1. Calculate target rotated coordinate dynamically using normalized unit coordinates scaled by sphereRadius
            const bx = p.ux * sphereRadius;
            const by = p.uy * sphereRadius;
            const bz = p.uz * sphereRadius;

            let tx1 = bx * cosY - bz * sinY;
            let tz1 = bx * sinY + bz * cosY;
            let ty = by * cosX - tz1 * sinX;
            let tx = tx1;
            let tz = by * sinX + tz1 * cosX;

            // 2. State & Position updates with bounding constraints
            if (animationState === "SPHERE") {
                p.x = tx;
                p.y = ty;
                p.z = tz;
            } else {
                // Apply velocity updates for BURST and ROAM states
                if (animationState === "BURST") {
                    p.x += p.vx;
                    p.y += p.vy;
                    p.z += p.vz;
                    // Apply drag
                    p.vx *= 0.96;
                    p.vy *= 0.96;
                    p.vz *= 0.96;
                } else if (animationState === "ROAM") {
                    p.x += p.vx;
                    p.y += p.vy;
                    p.z += p.vz;
                    // Add minor random floating force (reduced from 0.08 to 0.04)
                    p.vx += (Math.random() - 0.5) * 0.04;
                    p.vy += (Math.random() - 0.5) * 0.04;
                    p.vz += (Math.random() - 0.5) * 0.04;
                    // Limit speed (reduced from 1.2 to 0.8)
                    const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy + p.vz * p.vz) || 1;
                    if (speed > 0.8) {
                        p.vx = (p.vx / speed) * 0.8;
                        p.vy = (p.vy / speed) * 0.8;
                        p.vz = (p.vz / speed) * 0.8;
                    }
                } else if (animationState === "REFORM") {
                    // Gravity attraction pull towards rotating sphere target (reduced from 0.06 to 0.025 for smoother reform)
                    p.x += (tx - p.x) * 0.025;
                    p.y += (ty - p.y) * 0.025;
                    p.z += (tz - p.z) * 0.025;
                }

                // Enforce bounds to prevent particles from escaping the window dimensions or going behind camera
                const dist = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z) || 1;
                const maxAllowedDist = 450; // Cap explosion radius safely to keep particles visible

                if (dist > maxAllowedDist) {
                    p.x = (p.x / dist) * maxAllowedDist;
                    p.y = (p.y / dist) * maxAllowedDist;
                    p.z = (p.z / dist) * maxAllowedDist;
                    p.vx *= -0.5; // bounce back gently
                    p.vy *= -0.5;
                    p.vz *= -0.5;
                }

                // Extra safety boundary clip for Z-plane to prevent division by zero / camera clipping
                if (p.z < -260) {
                    p.z = -260;
                    p.vz = Math.abs(p.vz) * 0.5;
                }
            }

            // 3. Perspective Projection divide
            const scale = fov / (fov + p.z);
            const sx = cx + p.x * scale;
            const sy = cy + p.y * scale;

            projected.push({
                sx: sx,
                sy: sy,
                z: p.z,
                scale: scale,
                colorShift: p.colorShift
            });
        }

        // Draw connecting mesh lines (nearest neighbors)
        // Draw lines between points that are physically close in 3D space
        const maxDist = 45; // Max 3D distance to draw link
        ctx.lineWidth = 0.5;

        for (let i = 0; i < projected.length; i++) {
            const p1 = projected[i];
            const orig1 = particles[i];

            // Limit comparison loops to optimize CPU
            for (let j = i + 1; j < projected.length; j++) {
                if (j - i > 12) break; // Approximate nearest neighbors only

                const p2 = projected[j];
                const orig2 = particles[j];

                // 3D Distance calculation
                const dx = orig1.x - orig2.x;
                const dy = orig1.y - orig2.y;
                const dz = orig1.z - orig2.z;
                const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

                if (dist < maxDist) {
                    const lineAlpha = (1 - dist / maxDist) * 0.15;
                    // Render lines brighter at front, dimmer at back
                    const zAvg = (p1.z + p2.z) / 2;
                    const finalAlpha = lineAlpha * (1 - zAvg / sphereRadius);

                    if (finalAlpha > 0.01) {
                        ctx.beginPath();
                        ctx.moveTo(p1.sx, p1.sy);
                        ctx.lineTo(p2.sx, p2.sy);

                        // Color selection: blend cyan/blue/purple
                        const gradient = ctx.createLinearGradient(p1.sx, p1.sy, p2.sx, p2.sy);
                        if (p1.colorShift > 0.5) {
                            gradient.addColorStop(0, `rgba(139, 92, 246, ${finalAlpha})`); // purple
                            gradient.addColorStop(1, `rgba(59, 130, 246, ${finalAlpha})`); // blue
                        } else {
                            gradient.addColorStop(0, `rgba(59, 130, 246, ${finalAlpha})`);  // blue
                            gradient.addColorStop(1, `rgba(16, 185, 129, ${finalAlpha})`); // green/emerald
                        }

                        ctx.strokeStyle = gradient;
                        ctx.stroke();
                    }
                }
            }
        }

        // Draw individual particle points
        for (let i = 0; i < projected.length; i++) {
            const p = projected[i];

            // Perspective fade (depth mapping)
            const alpha = 0.2 + 0.8 * (1 - (p.z + sphereRadius) / (2 * sphereRadius));
            const size = (p.scale * 2.2);

            ctx.beginPath();
            ctx.arc(p.sx, p.sy, size > 0.2 ? size : 0.2, 0, 2 * Math.PI);

            // Set color based on index division
            if (p.colorShift > 0.6) {
                ctx.fillStyle = `rgba(139, 92, 246, ${alpha})`; // Stark Purple
            } else if (p.colorShift > 0.3) {
                ctx.fillStyle = `rgba(59, 130, 246, ${alpha})`;  // Electric Blue
            } else {
                ctx.fillStyle = `rgba(16, 185, 129, ${alpha})`;  // Mint Emerald
            }

            ctx.fill();

            // Add a soft glow dot to highlighted front particles
            if (p.z < -sphereRadius * 0.7) {
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, size * 2.5, 0, 2 * Math.PI);
                ctx.fillStyle = p.colorShift > 0.6
                    ? `rgba(139, 92, 246, ${alpha * 0.15})`
                    : `rgba(59, 130, 246, ${alpha * 0.15})`;
                ctx.fill();
            }
        }

        requestAnimationFrame(animate);
    }

    // Start particle loop
    animate();

    // Smooth scroll for anchor clicks
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
});
