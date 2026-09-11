/**
 * GLOCK MODELS AGENCY — Procedural 3D Luxury Diamond & Agency Core
 * Built with Three.js (r128) + GSAP
 * High-End Agency Aesthetics: Diamond Gemstone, Orbital Rose Gold & Platinum Rings,
 * 4 Orbiting Model Crystals, Floating Sparkle Dust, and Interactive Luxury Themes.
 */

(function () {
  'use strict';

  function isWebGLAvailable() {
    try {
      const canvas = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
    } catch (e) {
      return false;
    }
  }

  const container = document.getElementById('webglContainer');
  if (!container || !isWebGLAvailable()) {
    console.warn('[3D Models] WebGL недоступен или контейнер не найден.');
    return;
  }

  let scene, camera, renderer;
  let mainGroup, diamondMesh, innerGem, ringGold, ringPlatinum, ringGlow;
  let modelSatellites = [];
  let particleSystem;
  let keyLight, fillLight, rimLight;

  // Темы оформления
  const THEMES = {
    rosegold: {
      accent: 0xf472b6,
      ambient: 0x240e1b,
      light: 0xfb7185,
      gold: 0xfbbf24,
      name: 'Rose Gold'
    },
    diamond: {
      accent: 0x00f0ff,
      ambient: 0x0a1428,
      light: 0x38bdf8,
      gold: 0xe2e8f0,
      name: 'Diamond Ice'
    },
    ruby: {
      accent: 0xf43f5e,
      ambient: 0x280a12,
      light: 0xff4d6d,
      gold: 0xf59e0b,
      name: 'Ruby Passion'
    },
    emerald: {
      accent: 0x10b981,
      ambient: 0x062016,
      light: 0x34d399,
      gold: 0xfcd34d,
      name: 'Emerald VIP'
    }
  };

  let activeThemeKey = localStorage.getItem('botshop_3d_theme') || 'rosegold';
  if (!THEMES[activeThemeKey]) activeThemeKey = 'rosegold';

  const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
  const clock = new THREE.Clock();

  init();
  animate();

  function init() {
    const width = container.clientWidth || container.offsetWidth || 500;
    const height = container.clientHeight || container.offsetHeight || 500;

    // 1. Сцена
    scene = new THREE.Scene();

    // 2. Камера
    const aspect = width / height;
    camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 100);
    camera.position.set(0, 0, 7.8);

    // 3. Рендерер
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    const curTheme = THEMES[activeThemeKey];

    // 4. Освещение (Студийная схема для ювелирного блеска и отражений)
    const ambientLight = new THREE.AmbientLight(curTheme.ambient, 2.5);
    scene.add(ambientLight);

    keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    keyLight.position.set(5, 6, 5);
    scene.add(keyLight);

    fillLight = new THREE.DirectionalLight(curTheme.light, 1.6);
    fillLight.position.set(-6, -2, 4);
    scene.add(fillLight);

    rimLight = new THREE.PointLight(curTheme.accent, 4.0, 25);
    rimLight.position.set(0, 2, -4);
    scene.add(rimLight);

    // 5. Главная группа
    mainGroup = new THREE.Group();
    scene.add(mainGroup);

    // А. Центральный граненый бриллиант (Diamond Core)
    const diamondGeo = new THREE.OctahedronGeometry(1.65, 1);
    const diamondMat = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0.12,
      roughness: 0.06,
      transmission: 0.82,
      thickness: 1.8,
      ior: 2.417, // Реальный коэффициент преломления натурального алмаза
      clearcoat: 1.0,
      clearcoatRoughness: 0.04,
      reflectivity: 0.95,
      flatShading: true
    });
    diamondMesh = new THREE.Mesh(diamondGeo, diamondMat);
    mainGroup.add(diamondMesh);

    // Б. Внутреннее светящееся ядро (Кристалл страсти / Glamour Core)
    const innerGeo = new THREE.IcosahedronGeometry(0.85, 0);
    const innerMat = new THREE.MeshBasicMaterial({
      color: curTheme.accent,
      wireframe: true,
      transparent: true,
      opacity: 0.88
    });
    innerGem = new THREE.Mesh(innerGeo, innerMat);
    mainGroup.add(innerGem);

    // В. Внутренняя сверкающая микросфера
    const sparkPoint = new THREE.Mesh(
      new THREE.SphereGeometry(0.28, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xffffff })
    );
    mainGroup.add(sparkPoint);

    // Г. Орбитальное ювелирное кольцо из розового/желтого золота (Rose Gold Torus)
    const goldMat = new THREE.MeshPhysicalMaterial({
      color: curTheme.gold,
      metalness: 0.95,
      roughness: 0.12,
      clearcoat: 0.9
    });
    ringGold = new THREE.Mesh(new THREE.TorusGeometry(2.35, 0.042, 16, 100), goldMat);
    ringGold.rotation.x = Math.PI / 3.2;
    ringGold.rotation.y = Math.PI / 8;
    mainGroup.add(ringGold);

    // Д. Орбитальное кольцо из платины (Platinum Torus)
    const platMat = new THREE.MeshPhysicalMaterial({
      color: 0xf1f5f9,
      metalness: 0.92,
      roughness: 0.18,
      clearcoat: 0.8
    });
    ringPlatinum = new THREE.Mesh(new THREE.TorusGeometry(2.75, 0.032, 16, 100), platMat);
    ringPlatinum.rotation.x = -Math.PI / 4;
    ringPlatinum.rotation.z = Math.PI / 6;
    mainGroup.add(ringPlatinum);

    // Е. Тонкий светящийся акцентный нимб
    const glowMat = new THREE.MeshBasicMaterial({
      color: curTheme.accent,
      transparent: true,
      opacity: 0.4,
      wireframe: true
    });
    ringGlow = new THREE.Mesh(new THREE.TorusGeometry(3.15, 0.015, 8, 80), glowMat);
    ringGlow.rotation.y = Math.PI / 3;
    mainGroup.add(ringGlow);

    // Ж. 4 парящих кристалла-сателлита (Модели Агентства)
    const satGeo = new THREE.OctahedronGeometry(0.26, 0);
    const satMat = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0.2,
      roughness: 0.1,
      clearcoat: 1.0,
      flatShading: true
    });

    for (let i = 0; i < 4; i++) {
      const sat = new THREE.Mesh(satGeo, satMat);
      sat.userData = {
        angle: (i * Math.PI) / 2,
        speed: 0.65 + i * 0.15,
        radiusX: 3.2 + (i % 2) * 0.4,
        radiusY: 2.1 + (i % 2) * 0.3,
        inclination: (i * Math.PI) / 4
      };
      mainGroup.add(sat);
      modelSatellites.push(sat);
    }

    // З. Облако мерцающей звездной пыли (Sparkle Stardust)
    const partCount = 500;
    const partGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(partCount * 3);
    for (let i = 0; i < partCount * 3; i += 3) {
      const radius = 2.4 + Math.random() * 4.2;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i + 2] = radius * Math.cos(phi);
    }
    partGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const partMat = new THREE.PointsMaterial({
      size: 0.05,
      color: curTheme.accent,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending
    });
    particleSystem = new THREE.Points(partGeo, partMat);
    mainGroup.add(particleSystem);

    window.addEventListener('mousemove', onMouseMove, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('resize', onWindowResize, { passive: true });
    setupScrollAnimation();
  }

  function onMouseMove(e) {
    const rect = container.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    mouse.targetX = (e.clientX - cx) / (window.innerWidth * 0.5);
    mouse.targetY = (e.clientY - cy) / (window.innerHeight * 0.5);
  }

  function onTouchMove(e) {
    if (e.touches && e.touches.length > 0) {
      const touch = e.touches[0];
      const rect = container.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      mouse.targetX = (touch.clientX - cx) / (window.innerWidth * 0.5);
      mouse.targetY = (touch.clientY - cy) / (window.innerHeight * 0.5);
    }
  }

  function onWindowResize() {
    if (!container || !renderer || !camera) return;
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  function setupScrollAnimation() {
    if (window.gsap && window.ScrollTrigger && mainGroup) {
      gsap.registerPlugin(ScrollTrigger);

      gsap.to(mainGroup.position, {
        y: -1.0,
        scrollTrigger: {
          trigger: '#story',
          start: 'top bottom',
          end: 'bottom top',
          scrub: 1.2
        }
      });

      gsap.to(mainGroup.rotation, {
        y: Math.PI * 1.5,
        scrollTrigger: {
          trigger: '#story',
          start: 'top bottom',
          end: 'bottom top',
          scrub: 1.2
        }
      });

      gsap.to(mainGroup.scale, {
        x: 0.55,
        y: 0.55,
        z: 0.55,
        scrollTrigger: {
          trigger: '.categories-section',
          start: 'top 85%',
          end: 'top 20%',
          scrub: 1.0
        }
      });
    } else {
      window.addEventListener('scroll', () => {
        const scrollY = window.scrollY || window.pageYOffset;
        const maxScroll = 800;
        const progress = Math.min(scrollY / maxScroll, 1);

        if (mainGroup) {
          mainGroup.position.y = -progress * 0.8;
          mainGroup.rotation.y = progress * 1.5;
          mainGroup.scale.setScalar(1 - progress * 0.4);
        }
      }, { passive: true });
    }
  }

  function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    const elapsedTime = clock.getElapsedTime();

    mouse.x += (mouse.targetX - mouse.x) * 0.05;
    mouse.y += (mouse.targetY - mouse.y) * 0.05;

    if (mainGroup) {
      mainGroup.rotation.y = elapsedTime * 0.35 + mouse.x * 0.6;
      mainGroup.rotation.x = Math.sin(elapsedTime * 0.25) * 0.15 + mouse.y * 0.4;
    }

    if (diamondMesh) {
      diamondMesh.rotation.y += delta * 0.2;
      diamondMesh.rotation.z = Math.sin(elapsedTime * 0.5) * 0.08;
    }

    if (innerGem) {
      innerGem.rotation.y -= delta * 0.4;
      innerGem.rotation.x += delta * 0.3;
    }

    if (ringGold) {
      ringGold.rotation.z += delta * 0.45;
    }

    if (ringPlatinum) {
      ringPlatinum.rotation.z -= delta * 0.35;
    }

    if (ringGlow) {
      ringGlow.rotation.x += delta * 0.25;
    }

    modelSatellites.forEach((sat) => {
      const d = sat.userData;
      const angle = elapsedTime * d.speed + d.angle;
      sat.position.x = Math.cos(angle) * d.radiusX;
      sat.position.y = Math.sin(angle) * d.radiusY * Math.cos(d.inclination);
      sat.position.z = Math.sin(angle) * d.radiusY * Math.sin(d.inclination);
      sat.rotation.x += delta * 1.5;
      sat.rotation.y += delta * 2.0;
    });

    if (particleSystem) {
      particleSystem.rotation.y = -elapsedTime * 0.08;
    }

    renderer.render(scene, camera);
  }

  window.setAgency3DTheme = function (themeKey) {
    if (!THEMES[themeKey]) return;
    activeThemeKey = themeKey;
    localStorage.setItem('botshop_3d_theme', themeKey);
    const t = THEMES[themeKey];

    if (innerGem) innerGem.material.color.setHex(t.accent);
    if (ringGlow) ringGlow.material.color.setHex(t.accent);
    if (particleSystem) particleSystem.material.color.setHex(t.accent);
    if (rimLight) rimLight.color.setHex(t.accent);
    if (fillLight) fillLight.color.setHex(t.light);
    if (ringGold) ringGold.material.color.setHex(t.gold);

    document.querySelectorAll('.theme-btn-chip').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.theme === themeKey);
    });
  };

})();
