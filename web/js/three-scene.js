/**
 * GLOCK MODELS AGENCY — 3D Runway Haute Couture Model & Catwalk Scene
 * Built with Three.js (r128) + GSAP
 * High-Fashion Aesthetics: Statuesque Runway Model Mannequin, Mirror Catwalk Podium,
 * Floating Silk Ribbon, Orbiting Agency Lookbook Cards, Studio Rim Lights & Paparazzi Flashes.
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
  let mainGroup, modelGroup, catwalkGroup, ribbonMesh, ribbonCurve;
  let modelMaterials = [];
  let floatingCards = [];
  let particleDust;
  let keyLight, fillLight, rimLight1, rimLight2, floorLight, paparazziFlash;

  // Темы оформления
  const THEMES = {
    rosegold: {
      accent: 0xf472b6,
      ambient: 0x1f0e1a,
      light: 0xfb7185,
      gold: 0xfbbf24,
      modelColor: 0x22131d,
      modelEmissive: 0x2a0d1e,
      roughness: 0.18,
      metalness: 0.85,
      name: 'Rose Gold'
    },
    diamond: {
      accent: 0x00f0ff,
      ambient: 0x081320,
      light: 0x38bdf8,
      gold: 0xe2e8f0,
      modelColor: 0x0e1824,
      modelEmissive: 0x081b2a,
      roughness: 0.12,
      metalness: 0.92,
      name: 'Diamond Ice'
    },
    ruby: {
      accent: 0xf43f5e,
      ambient: 0x22080f,
      light: 0xff4d6d,
      gold: 0xf59e0b,
      modelColor: 0x240910,
      modelEmissive: 0x2f0813,
      roughness: 0.16,
      metalness: 0.86,
      name: 'Ruby Passion'
    },
    emerald: {
      accent: 0x10b981,
      ambient: 0x051a12,
      light: 0x34d399,
      gold: 0xfcd34d,
      modelColor: 0x081b13,
      modelEmissive: 0x062419,
      roughness: 0.18,
      metalness: 0.88,
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
    const width = container.clientWidth || window.innerWidth || 500;
    const height = container.clientHeight || window.innerHeight || 500;

    // 1. Сцена
    scene = new THREE.Scene();

    // 2. Камера (Hero fashion angle — чуть снизу вверх)
    const aspect = width / height;
    camera = new THREE.PerspectiveCamera(42, aspect, 0.1, 100);
    camera.position.set(0, 0.4, 5.8);

    // 3. Рендерер
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    const curTheme = THEMES[activeThemeKey];

    // 4. Студийный свет высокой моды (Vogue / Catwalk Studio Rig)
    const ambientLight = new THREE.AmbientLight(curTheme.ambient, 2.2);
    scene.add(ambientLight);

    // Основной моделирующий свет (Key Light)
    keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    keyLight.position.set(3, 5, 4);
    scene.add(keyLight);

    // Заполняющий свет (Fill Light)
    fillLight = new THREE.DirectionalLight(curTheme.light, 1.4);
    fillLight.position.set(-4, -1, 3);
    scene.add(fillLight);

    // Контровые прожекторы (Rim Lights - дают тот самый сияющий неоновый контур по телу)
    rimLight1 = new THREE.PointLight(curTheme.accent, 4.2, 18);
    rimLight1.position.set(2.5, 1.2, -2.5);
    scene.add(rimLight1);

    rimLight2 = new THREE.PointLight(curTheme.light, 3.2, 18);
    rimLight2.position.set(-2.5, 0.5, -2.5);
    scene.add(rimLight2);

    // Нижняя подсветка от зеркального подиума
    floorLight = new THREE.PointLight(curTheme.accent, 1.8, 8);
    floorLight.position.set(0, -1.8, 0.5);
    scene.add(floorLight);

    // Вспышка папарацци (Paparazzi Flash)
    paparazziFlash = new THREE.PointLight(0xffffff, 0, 15);
    paparazziFlash.position.set(-3, 2, -1);
    scene.add(paparazziFlash);

    // 5. Главная группа сцены
    mainGroup = new THREE.Group();
    scene.add(mainGroup);

    // 6. Зеркальный подиум (Catwalk Mirror Runway)
    createCatwalkPodium(curTheme);

    // 7. Подиумная модель (Haute Couture 3D Mannequin)
    createFashionModel(curTheme);

    // 8. Развевающаяся шёлковая лента (Floating Silk Ribbon)
    createSilkRibbon(curTheme);

    // 9. Парящие карточки лукбука (Orbiting Agency Lookbook Cards)
    createLookbookCards(curTheme);

    // 10. Атмосферная золотистая пыльца (Backstage Glitter Dust)
    createGlitterDust(curTheme);

    // События
    window.addEventListener('resize', onWindowResize, false);
    window.addEventListener('mousemove', onMouseMove, false);
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });

    window.setAgency3DTheme = setAgency3DTheme;
    updateActiveThemeButtons(activeThemeKey);
  }

  // ==========================================
  // ЗЕРКАЛЬНЫЙ ПОДИУМ (CATWALK PODIUM)
  // ==========================================
  function createCatwalkPodium(theme) {
    catwalkGroup = new THREE.Group();
    catwalkGroup.position.y = -1.95;

    // Главный диск подиума (черный зеркальный обсидиан)
    const podiumGeo = new THREE.CylinderGeometry(2.1, 2.3, 0.12, 64);
    const podiumMat = new THREE.MeshStandardMaterial({
      color: 0x0a0c12,
      roughness: 0.15,
      metalness: 0.85
    });
    const podium = new THREE.Mesh(podiumGeo, podiumMat);
    catwalkGroup.add(podium);

    // Неоновое кольцо по краю подиума
    const ringGeo = new THREE.TorusGeometry(2.31, 0.022, 16, 100);
    const ringMat = new THREE.MeshBasicMaterial({
      color: theme.accent,
      transparent: true,
      opacity: 0.85
    });
    catwalkGroup.podiumRingMat = ringMat;
    const rimRing = new THREE.Mesh(ringGeo, ringMat);
    rimRing.rotation.x = Math.PI / 2;
    rimRing.position.y = 0.05;
    catwalkGroup.add(rimRing);

    // Внутреннее золотое кольцо
    const innerRingGeo = new THREE.TorusGeometry(1.6, 0.015, 16, 80);
    const innerRingMat = new THREE.MeshStandardMaterial({
      color: theme.gold,
      roughness: 0.2,
      metalness: 0.9
    });
    catwalkGroup.innerRingMat = innerRingMat;
    const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
    innerRing.rotation.x = Math.PI / 2;
    innerRing.position.y = 0.062;
    catwalkGroup.add(innerRing);

    // Мягкий световой ореол под ногами
    const haloGeo = new THREE.CircleGeometry(1.4, 48);
    const haloMat = new THREE.MeshBasicMaterial({
      color: theme.accent,
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide
    });
    catwalkGroup.haloMat = haloMat;
    const halo = new THREE.Mesh(haloGeo, haloMat);
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = 0.065;
    catwalkGroup.add(halo);

    mainGroup.add(catwalkGroup);
  }

  // ==========================================
  // ПОДИУМНАЯ 3D МОДЕЛЬ (HAUTE COUTURE MANNEQUIN)
  // ==========================================
  function createFashionModel(theme) {
    modelGroup = new THREE.Group();
    modelGroup.position.set(0, -0.15, 0);

    // Материал модели (Glossy Liquid Chrome / Rose Gold / Pearl)
    const modelMat = new THREE.MeshPhysicalMaterial({
      color: theme.modelColor,
      emissive: theme.modelEmissive,
      roughness: theme.roughness,
      metalness: theme.metalness,
      clearcoat: 1.0,
      clearcoatRoughness: 0.1,
      reflectivity: 0.95
    });
    modelMaterials.push(modelMat);

    // 1. ГОЛОВА И ПРИЧЕСКА
    const headGroup = new THREE.Group();
    headGroup.position.y = 1.95;

    // Стилизованная изящная голова модели
    const headGeo = new THREE.SphereGeometry(0.22, 32, 24);
    headGeo.scale(0.85, 1.15, 0.92);
    const head = new THREE.Mesh(headGeo, modelMat);
    headGroup.add(head);

    // Гладкая высокая прическа / подиумный пучок (Chignon)
    const hairGeo = new THREE.SphereGeometry(0.17, 24, 18);
    hairGeo.scale(0.9, 1.0, 1.15);
    const hair = new THREE.Mesh(hairGeo, modelMat);
    hair.position.set(0, 0.08, -0.11);
    headGroup.add(hair);

    // Лебединая шея
    const neckGeo = new THREE.CylinderGeometry(0.085, 0.11, 0.35, 32);
    const neck = new THREE.Mesh(neckGeo, modelMat);
    neck.position.y = 1.68;
    modelGroup.add(neck);

    // Золотое колье / чокер
    const chokerGeo = new THREE.TorusGeometry(0.105, 0.018, 16, 40);
    const chokerMat = new THREE.MeshStandardMaterial({
      color: theme.gold,
      metalness: 0.95,
      roughness: 0.15
    });
    modelGroup.chokerMat = chokerMat;
    const choker = new THREE.Mesh(chokerGeo, chokerMat);
    choker.rotation.x = Math.PI / 2;
    choker.position.y = 1.65;
    modelGroup.add(choker);

    modelGroup.add(headGroup);

    // 2. ИЗЯЩНОЕ ТОРСО И КОРСЕТ (HAUTE COUTURE CURVES)
    const curvePoints = [
      new THREE.Vector2(0.12, 1.52),  // Основание шеи / ключицы
      new THREE.Vector2(0.38, 1.44),  // Линия плеч
      new THREE.Vector2(0.34, 1.34),  // Верх груди
      new THREE.Vector2(0.36, 1.22),  // Бюст
      new THREE.Vector2(0.28, 1.08),  // Под грудью
      new THREE.Vector2(0.21, 0.92),  // Узкая талия (cinched waist)
      new THREE.Vector2(0.29, 0.76),  // Верх бедер
      new THREE.Vector2(0.38, 0.58),  // Линия бедер (femme curves)
      new THREE.Vector2(0.36, 0.44),  // Основание бедер
      new THREE.Vector2(0.28, 0.32)   // Схождение к ногам
    ];
    const torsoGeo = new THREE.LatheGeometry(curvePoints, 48);
    torsoGeo.scale(1.0, 1.0, 0.72);
    const torso = new THREE.Mesh(torsoGeo, modelMat);
    torso.position.y = 0.05;
    modelGroup.add(torso);

    // Золотой пояс на талии
    const waistBeltGeo = new THREE.TorusGeometry(0.23, 0.02, 16, 48);
    waistBeltGeo.scale(1.0, 0.7, 1.0);
    const waistBelt = new THREE.Mesh(waistBeltGeo, chokerMat);
    waistBelt.rotation.x = Math.PI / 2;
    waistBelt.position.y = 0.97;
    modelGroup.add(waistBelt);

    // 3. РУКИ В ПОДИУМНОЙ ПОЗЕ (RUNWAY POSE)
    // Левая рука: согнута в локте с ладонью на талии
    const leftArmGroup = new THREE.Group();
    leftArmGroup.position.set(0.36, 1.40, 0);

    const leftUpperArmGeo = new THREE.CylinderGeometry(0.06, 0.05, 0.52, 24);
    const leftUpperArm = new THREE.Mesh(leftUpperArmGeo, modelMat);
    leftUpperArm.position.set(0.12, -0.22, 0.05);
    leftUpperArm.rotation.z = -0.55;
    leftUpperArm.rotation.x = 0.2;
    leftArmGroup.add(leftUpperArm);

    const leftForearmGeo = new THREE.CylinderGeometry(0.05, 0.04, 0.48, 24);
    const leftForearm = new THREE.Mesh(leftForearmGeo, modelMat);
    leftForearm.position.set(0.18, -0.42, 0.16);
    leftForearm.rotation.z = 0.75;
    leftForearm.rotation.x = -0.35;
    leftArmGroup.add(leftForearm);

    // Золотой браслет на руке
    const braceletGeo = new THREE.TorusGeometry(0.055, 0.012, 12, 32);
    const bracelet = new THREE.Mesh(braceletGeo, chokerMat);
    bracelet.position.set(0.10, -0.46, 0.18);
    leftArmGroup.add(bracelet);

    modelGroup.add(leftArmGroup);

    // Правая рука: грациозно опущена вдоль бедра в шаге
    const rightArmGroup = new THREE.Group();
    rightArmGroup.position.set(-0.36, 1.40, 0);

    const rightUpperArmGeo = new THREE.CylinderGeometry(0.06, 0.05, 0.54, 24);
    const rightUpperArm = new THREE.Mesh(rightUpperArmGeo, modelMat);
    rightUpperArm.position.set(-0.06, -0.24, -0.04);
    rightUpperArm.rotation.z = 0.22;
    rightUpperArm.rotation.x = -0.15;
    rightArmGroup.add(rightUpperArm);

    const rightForearmGeo = new THREE.CylinderGeometry(0.05, 0.04, 0.50, 24);
    const rightForearm = new THREE.Mesh(rightForearmGeo, modelMat);
    rightForearm.position.set(-0.11, -0.66, -0.06);
    rightForearm.rotation.z = 0.10;
    rightArmGroup.add(rightForearm);

    modelGroup.add(rightArmGroup);

    // 4. СТРОЙНЫЕ ДЛИННЫЕ НОГИ В ПОДИУМНОМ ШАГЕ
    // Опорная нога (правая): вытянута вертикально
    const rightLegGroup = new THREE.Group();
    rightLegGroup.position.set(-0.13, 0.35, 0);

    const rightThighGeo = new THREE.CylinderGeometry(0.135, 0.09, 0.90, 24);
    const rightThigh = new THREE.Mesh(rightThighGeo, modelMat);
    rightThigh.position.y = -0.42;
    rightLegGroup.add(rightThigh);

    const rightShinGeo = new THREE.CylinderGeometry(0.085, 0.055, 0.95, 24);
    const rightShin = new THREE.Mesh(rightShinGeo, modelMat);
    rightShin.position.y = -1.28;
    rightLegGroup.add(rightShin);

    // Туфля на шпильке (правая)
    const rightShoeGeo = new THREE.ConeGeometry(0.08, 0.22, 16);
    rightShoeGeo.scale(0.8, 1.0, 1.6);
    const rightShoe = new THREE.Mesh(rightShoeGeo, chokerMat);
    rightShoe.rotation.x = Math.PI / 2.2;
    rightShoe.position.set(0, -1.78, 0.08);
    rightLegGroup.add(rightShoe);

    const heelGeo = new THREE.CylinderGeometry(0.015, 0.01, 0.26, 12);
    const rightHeel = new THREE.Mesh(heelGeo, chokerMat);
    rightHeel.position.set(0, -1.80, -0.04);
    rightLegGroup.add(rightHeel);

    modelGroup.add(rightLegGroup);

    // Шагающая нога (левая): вынесена слегка вперед
    const leftLegGroup = new THREE.Group();
    leftLegGroup.position.set(0.13, 0.35, 0);

    const leftThighGeo = new THREE.CylinderGeometry(0.135, 0.09, 0.90, 24);
    const leftThigh = new THREE.Mesh(leftThighGeo, modelMat);
    leftThigh.position.set(0.02, -0.42, 0.10);
    leftThigh.rotation.x = -0.22;
    leftLegGroup.add(leftThigh);

    const leftShinGeo = new THREE.CylinderGeometry(0.085, 0.055, 0.95, 24);
    const leftShin = new THREE.Mesh(leftShinGeo, modelMat);
    leftShin.position.set(0.02, -1.26, 0.25);
    leftShin.rotation.x = -0.08;
    leftLegGroup.add(leftShin);

    const leftShoe = new THREE.Mesh(rightShoeGeo, chokerMat);
    leftShoe.rotation.x = Math.PI / 2.1;
    leftShoe.position.set(0.02, -1.77, 0.34);
    leftLegGroup.add(leftShoe);

    const leftHeel = new THREE.Mesh(heelGeo, chokerMat);
    leftHeel.position.set(0.02, -1.79, 0.22);
    leftLegGroup.add(leftHeel);

    modelGroup.add(leftLegGroup);

    mainGroup.add(modelGroup);
  }

  // ==========================================
  // РАЗВЕВАЮЩАЯСЯ ШЁЛКОВАЯ ЛЕНТА (SILK RIBBON)
  // ==========================================
  function createSilkRibbon(theme) {
    const splinePoints = [
      new THREE.Vector3(0.0, -1.8, -0.6),
      new THREE.Vector3(0.8, -1.3, 0.2),
      new THREE.Vector3(0.4, -0.7, 0.7),
      new THREE.Vector3(-0.7, -0.2, 0.4),
      new THREE.Vector3(-0.6, 0.4, -0.5),
      new THREE.Vector3(0.5, 0.9, -0.3),
      new THREE.Vector3(0.7, 1.4, 0.4),
      new THREE.Vector3(0.2, 1.8, 0.6),
      new THREE.Vector3(-0.4, 2.1, 0.2)
    ];

    ribbonCurve = new THREE.CatmullRomCurve3(splinePoints);
    ribbonCurve.curveType = 'centripetal';

    const tubeGeo = new THREE.TubeGeometry(ribbonCurve, 120, 0.038, 16, false);
    const ribbonMat = new THREE.MeshPhysicalMaterial({
      color: theme.accent,
      emissive: theme.accent,
      emissiveIntensity: 0.35,
      roughness: 0.25,
      metalness: 0.65,
      transparent: true,
      opacity: 0.85,
      clearcoat: 1.0
    });
    mainGroup.ribbonMat = ribbonMat;

    ribbonMesh = new THREE.Mesh(tubeGeo, ribbonMat);
    mainGroup.add(ribbonMesh);
  }

  // ==========================================
  // ПАРЯЩИЕ КАРТОЧКИ ЛУКБУКА (LOOKBOOK CARDS)
  // ==========================================
  function createLookbookCards(theme) {
    const cardData = [
      { text: '💎 VIP 4K', sub: 'EXCLUSIVE', angle: 0, height: 1.1, radius: 1.85 },
      { text: '✨ GLOCK MODELS', sub: 'AGENCY 2026', angle: Math.PI * 0.55, height: 0.3, radius: 1.95 },
      { text: '🔞 1000+ MEDIA', sub: 'DAILY ARCHIVE', angle: Math.PI * 1.1, height: 1.4, radius: 1.9 },
      { text: '🦋 PRIVATE ACCESS', sub: 'VERIFIED', angle: Math.PI * 1.65, height: -0.4, radius: 1.8 }
    ];

    cardData.forEach((item, index) => {
      const canvas = document.createElement('canvas');
      canvas.width = 380;
      canvas.height = 140;
      const ctx = canvas.getContext('2d');

      const grad = ctx.createLinearGradient(0, 0, 380, 140);
      grad.addColorStop(0, 'rgba(25, 18, 30, 0.88)');
      grad.addColorStop(1, 'rgba(12, 10, 18, 0.94)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect(0, 0, 380, 140, 18);
      ctx.fill();

      ctx.strokeStyle = '#f472b6';
      ctx.lineWidth = 4;
      ctx.stroke();

      ctx.font = 'bold 30px "JetBrains Mono", Inter, sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(item.text, 24, 60);

      ctx.font = '600 16px Inter, sans-serif';
      ctx.fillStyle = '#f472b6';
      ctx.fillText(item.sub, 26, 100);

      const texture = new THREE.CanvasTexture(canvas);
      texture.generateMipmaps = true;

      const cardGeo = new THREE.PlaneGeometry(0.85, 0.32);
      const cardMat = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        opacity: 0.92,
        side: THREE.DoubleSide
      });

      const cardMesh = new THREE.Mesh(cardGeo, cardMat);
      cardMesh.cardItem = item;
      cardMesh.canvas = canvas;
      cardMesh.ctx = ctx;
      cardMesh.texture = texture;

      floatingCards.push(cardMesh);
      mainGroup.add(cardMesh);
    });
  }

  // ==========================================
  // АТМОСФЕРНАЯ ПЫЛЬЦА (GLITTER PARTICLES)
  // ==========================================
  function createGlitterDust(theme) {
    const particleCount = 140;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const scales = new Float32Array(particleCount);

    for (let i = 0; i < particleCount; i++) {
      const theta = Math.random() * Math.PI * 2;
      const radius = 0.8 + Math.random() * 2.8;
      positions[i * 3] = Math.cos(theta) * radius;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 4.6;
      positions[i * 3 + 2] = Math.sin(theta) * radius;
      scales[i] = 0.5 + Math.random() * 1.5;
    }

    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('scale', new THREE.BufferAttribute(scales, 1));

    const mat = new THREE.PointsMaterial({
      color: theme.accent,
      size: 0.045,
      transparent: true,
      opacity: 0.7,
      blending: THREE.AdditiveBlending
    });
    mainGroup.dustMat = mat;

    particleDust = new THREE.Points(geom, mat);
    mainGroup.add(particleDust);
  }

  // ==========================================
  // АНИМАЦИЯ И РЕНДЕР-ЦИКЛ
  // ==========================================
  let nextFlashTime = 3.0;

  function animate() {
    requestAnimationFrame(animate);

    const elapsedTime = clock.getElapsedTime();

    // 1. Плавное следование за курсором мыши (Parallax & Turn)
    mouse.x += (mouse.targetX - mouse.x) * 0.04;
    mouse.y += (mouse.targetY - mouse.y) * 0.04;

    if (mainGroup) {
      mainGroup.rotation.y = Math.sin(elapsedTime * 0.4) * 0.18 + (mouse.x * 0.45);
      mainGroup.position.x = mouse.x * 0.25;
      mainGroup.position.y = -mouse.y * 0.15;
    }

    // 2. Дыхание и микро-движения подиумной модели
    if (modelGroup) {
      modelGroup.position.y = -0.15 + Math.sin(elapsedTime * 1.2) * 0.025;
      modelGroup.rotation.z = Math.sin(elapsedTime * 0.6) * 0.02;
    }

    // 3. Анимация парящей шёлковой ленты
    if (ribbonMesh) {
      ribbonMesh.rotation.y = -elapsedTime * 0.25;
      ribbonMesh.position.y = Math.sin(elapsedTime * 0.9) * 0.04;
    }

    // 4. Орбита карточек лукбука
    floatingCards.forEach((card, i) => {
      const item = card.cardItem;
      const curAngle = item.angle + (elapsedTime * 0.22);
      const r = item.radius;
      card.position.x = Math.cos(curAngle) * r;
      card.position.z = Math.sin(curAngle) * r;
      card.position.y = item.height + Math.sin(elapsedTime * 1.5 + i) * 0.08;
      card.lookAt(camera.position);
    });

    // 5. Вращение золотистой пыльцы
    if (particleDust) {
      particleDust.rotation.y = elapsedTime * 0.05;
    }

    // 6. Вспышки папарацци (Catwalk Flashes)
    if (elapsedTime > nextFlashTime) {
      triggerPaparazziFlash();
      nextFlashTime = elapsedTime + 2.5 + Math.random() * 4.0;
    }
    if (paparazziFlash && paparazziFlash.intensity > 0) {
      paparazziFlash.intensity *= 0.88;
      if (paparazziFlash.intensity < 0.05) paparazziFlash.intensity = 0;
    }

    renderer.render(scene, camera);
  }

  function triggerPaparazziFlash() {
    if (!paparazziFlash) return;
    paparazziFlash.position.set(
      (Math.random() - 0.5) * 6,
      0.5 + Math.random() * 3,
      -1.5 - Math.random() * 2
    );
    paparazziFlash.intensity = 4.5 + Math.random() * 3.5;
  }

  // ==========================================
  // ОБРАБОТЧИКИ СОБЫТИЙ
  // ==========================================
  function onMouseMove(event) {
    mouse.targetX = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.targetY = -(event.clientY / window.innerHeight) * 2 + 1;
  }

  function onTouchMove(event) {
    if (event.touches.length > 0) {
      const touch = event.touches[0];
      mouse.targetX = (touch.clientX / window.innerWidth) * 2 - 1;
      mouse.targetY = -(touch.clientY / window.innerHeight) * 2 + 1;
    }
  }

  function onWindowResize() {
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  function onScroll() {
    const scrollY = window.pageYOffset || document.documentElement.scrollTop;
    if (mainGroup) {
      const scrollProgress = Math.min(scrollY / 700, 1);
      mainGroup.scale.setScalar(1.0 - scrollProgress * 0.22);
      mainGroup.position.z = -scrollProgress * 1.5;
    }
  }

  // ==========================================
  // СМЕНА ТЕМ ОФОРМЛЕНИЯ В РЕАЛЬНОМ ВРЕМЕНИ
  // ==========================================
  function setAgency3DTheme(themeKey) {
    if (!THEMES[themeKey]) return;
    activeThemeKey = themeKey;
    localStorage.setItem('botshop_3d_theme', themeKey);
    const t = THEMES[themeKey];

    if (typeof gsap !== 'undefined') {
      gsap.to(rimLight1.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      gsap.to(rimLight2.color, { r: ((t.light >> 16) & 255) / 255, g: ((t.light >> 8) & 255) / 255, b: (t.light & 255) / 255, duration: 0.8 });
      gsap.to(floorLight.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      gsap.to(fillLight.color, { r: ((t.light >> 16) & 255) / 255, g: ((t.light >> 8) & 255) / 255, b: (t.light & 255) / 255, duration: 0.8 });

      modelMaterials.forEach(mat => {
        gsap.to(mat.color, { r: ((t.modelColor >> 16) & 255) / 255, g: ((t.modelColor >> 8) & 255) / 255, b: (t.modelColor & 255) / 255, duration: 0.8 });
        gsap.to(mat.emissive, { r: ((t.modelEmissive >> 16) & 255) / 255, g: ((t.modelEmissive >> 8) & 255) / 255, b: (t.modelEmissive & 255) / 255, duration: 0.8 });
      });

      if (mainGroup.ribbonMat) {
        gsap.to(mainGroup.ribbonMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
        gsap.to(mainGroup.ribbonMat.emissive, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }

      if (catwalkGroup && catwalkGroup.podiumRingMat) {
        gsap.to(catwalkGroup.podiumRingMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }
      if (catwalkGroup && catwalkGroup.haloMat) {
        gsap.to(catwalkGroup.haloMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }
      if (mainGroup.dustMat) {
        gsap.to(mainGroup.dustMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }
    }

    updateActiveThemeButtons(themeKey);
  }

  function updateActiveThemeButtons(activeKey) {
    document.querySelectorAll('.theme-btn-chip').forEach(btn => {
      if (btn.dataset.theme === activeKey) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

})();
