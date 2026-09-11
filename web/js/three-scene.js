/**
 * GLOCK MODELS AGENCY — 3D Runway Haute Couture Model & Catwalk Scene
 * Built with Three.js (r128) + GSAP
 * High-Fashion Aesthetics: Statuesque Runway Model Mannequin, Mirror Catwalk Podium,
 * Seamless Continuous Spline Arms & Curves, Silk Ribbon, Orbiting Lookbook Cards,
 * Studio Rim Lighting & Full Responsive Mobile Adaptation.
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

  // Cross-browser safe rounded rectangle drawing
  function drawRoundRect(ctx, x, y, w, h, r) {
    if (typeof ctx.roundRect === 'function') {
      ctx.beginPath();
      ctx.roundRect(x, y, w, h, r);
      return;
    }
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  let scene, camera, renderer;
  let mainGroup, modelGroup, catwalkGroup, ribbonMesh;
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
      modelColor: 0x24121f,
      modelEmissive: 0x2e0c20,
      roughness: 0.16,
      metalness: 0.86,
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
      roughness: 0.15,
      metalness: 0.88,
      name: 'Ruby Passion'
    },
    emerald: {
      accent: 0x10b981,
      ambient: 0x051a12,
      light: 0x34d399,
      gold: 0xfcd34d,
      modelColor: 0x081b13,
      modelEmissive: 0x062419,
      roughness: 0.17,
      metalness: 0.89,
      name: 'Emerald VIP'
    }
  };

  let activeThemeKey = localStorage.getItem('botshop_3d_theme') || 'rosegold';
  if (!THEMES[activeThemeKey]) activeThemeKey = 'rosegold';

  const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
  const clock = new THREE.Clock();

  try {
    init();
    animate();
    console.log('[3D Models] Haute Couture Runway Scene initialized successfully!');
  } catch (err) {
    console.error('[3D Models] Init Error:', err);
  }

  function init() {
    const width = window.innerWidth || 800;
    const height = window.innerHeight || 600;
    const isMobile = width < 768;

    // 1. Сцена
    scene = new THREE.Scene();

    // 2. Камера (адаптированная под мобильные и десктоп)
    const aspect = width / height;
    camera = new THREE.PerspectiveCamera(42, aspect, 0.1, 100);
    // На мобильных увеличиваем дистанцию, чтобы модель полностью помещалась в кадр
    const cameraZ = isMobile ? 7.6 : (width < 1024 ? 6.4 : 5.6);
    const cameraY = isMobile ? 0.05 : 0.25;
    camera.position.set(0, cameraY, cameraZ);

    // 3. Рендерер
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    const curTheme = THEMES[activeThemeKey];

    // 4. Студийный свет высокой моды
    const ambientLight = new THREE.AmbientLight(curTheme.ambient, 2.6);
    scene.add(ambientLight);

    keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
    keyLight.position.set(3, 5, 4);
    scene.add(keyLight);

    fillLight = new THREE.DirectionalLight(curTheme.light, 1.6);
    fillLight.position.set(-4, -1, 3);
    scene.add(fillLight);

    rimLight1 = new THREE.PointLight(curTheme.accent, 4.8, 20);
    rimLight1.position.set(2.8, 1.2, -2.2);
    scene.add(rimLight1);

    rimLight2 = new THREE.PointLight(curTheme.light, 3.8, 20);
    rimLight2.position.set(-2.8, 0.5, -2.2);
    scene.add(rimLight2);

    floorLight = new THREE.PointLight(curTheme.accent, 2.2, 10);
    floorLight.position.set(0, -1.8, 0.5);
    scene.add(floorLight);

    paparazziFlash = new THREE.PointLight(0xffffff, 0, 20);
    paparazziFlash.position.set(-3, 2, -1);
    scene.add(paparazziFlash);

    // 5. Главная группа сцены (адаптивное позиционирование)
    mainGroup = new THREE.Group();
    applyResponsiveLayout(width);
    scene.add(mainGroup);

    // 6. Зеркальный подиум (Catwalk Mirror Runway)
    createCatwalkPodium(curTheme);

    // 7. Подиумная модель (Haute Couture Mannequin с бесшовными анатомичными руками)
    createFashionModel(curTheme);

    // 8. Развевающаяся шёлковая лента (Floating Silk Ribbon)
    createSilkRibbon(curTheme);

    // 9. Парящие карточки лукбука (Orbiting Agency Lookbook Cards)
    createLookbookCards(curTheme, isMobile);

    // 10. Атмосферная золотистая пыльца (Backstage Glitter Dust)
    createGlitterDust(curTheme);

    // Слушатели событий
    window.addEventListener('resize', onWindowResize, false);
    window.addEventListener('mousemove', onMouseMove, false);
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });

    window.setAgency3DTheme = setAgency3DTheme;
    updateActiveThemeButtons(activeThemeKey);
  }

  // Адаптивное позиционирование и масштаб главной группы
  function applyResponsiveLayout(width) {
    if (!mainGroup) return;
    if (width < 600) {
      // Мобильный телефон: модель по центру, уменьшенный масштаб для 100% видимости
      mainGroup.position.set(0, -0.25, 0);
      mainGroup.scale.setScalar(0.74);
    } else if (width < 900) {
      // Планшет
      mainGroup.position.set(0.6, -0.15, 0);
      mainGroup.scale.setScalar(0.85);
    } else if (width < 1200) {
      // Ноутбук
      mainGroup.position.set(1.35, -0.05, 0);
      mainGroup.scale.setScalar(0.95);
    } else {
      // Большой десктоп: модель с правой стороны от Hero-баннера
      mainGroup.position.set(1.65, 0, 0);
      mainGroup.scale.setScalar(1.0);
    }
  }

  // ==========================================
  // ЗЕРКАЛЬНЫЙ ПОДИУМ (CATWALK PODIUM)
  // ==========================================
  function createCatwalkPodium(theme) {
    try {
      catwalkGroup = new THREE.Group();
      catwalkGroup.position.y = -1.95;

      const podiumGeo = new THREE.CylinderGeometry(2.1, 2.3, 0.12, 48);
      const podiumMat = new THREE.MeshStandardMaterial({
        color: 0x0a0c12,
        roughness: 0.15,
        metalness: 0.85
      });
      const podium = new THREE.Mesh(podiumGeo, podiumMat);
      catwalkGroup.add(podium);

      const ringGeo = new THREE.TorusGeometry(2.31, 0.025, 16, 80);
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

      const innerRingGeo = new THREE.TorusGeometry(1.5, 0.015, 16, 64);
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

      const haloGeo = new THREE.CircleGeometry(1.4, 36);
      const haloMat = new THREE.MeshBasicMaterial({
        color: theme.accent,
        transparent: true,
        opacity: 0.22,
        side: THREE.DoubleSide
      });
      catwalkGroup.haloMat = haloMat;
      const halo = new THREE.Mesh(haloGeo, haloMat);
      halo.rotation.x = -Math.PI / 2;
      halo.position.y = 0.065;
      catwalkGroup.add(halo);

      mainGroup.add(catwalkGroup);
    } catch (e) {
      console.warn('Catwalk podium error:', e);
    }
  }

  // ==========================================
  // ПОДИУМНАЯ 3D МОДЕЛЬ С КРАСИВЫМИ СГЛАЖЕННЫМИ РУКАМИ
  // ==========================================
  function createFashionModel(theme) {
    try {
      modelGroup = new THREE.Group();
      modelGroup.position.set(0, -0.15, 0);

      // Люксовый гладкий материал манекена
      const modelMat = new THREE.MeshPhysicalMaterial({
        color: theme.modelColor,
        emissive: theme.modelEmissive,
        roughness: theme.roughness,
        metalness: theme.metalness,
        clearcoat: 1.0,
        clearcoatRoughness: 0.08,
        reflectivity: 0.95,
        side: THREE.DoubleSide
      });
      modelMaterials.push(modelMat);

      // Золотой металл для украшений (чокер, пояс, браслеты, туфли)
      const goldMat = new THREE.MeshStandardMaterial({
        color: theme.gold,
        metalness: 0.95,
        roughness: 0.15
      });
      modelGroup.goldMat = goldMat;

      // 1. ГОЛОВА, ШЕЯ И ПРИЧЕСКА
      const headGroup = new THREE.Group();
      headGroup.position.y = 1.95;

      // Изящная овальная голова супермодели
      const headGeo = new THREE.SphereGeometry(0.21, 32, 24);
      headGeo.scale(0.85, 1.15, 0.92);
      const head = new THREE.Mesh(headGeo, modelMat);
      headGroup.add(head);

      // Гладкий высокий подиумный пучок (Chignon)
      const hairGeo = new THREE.SphereGeometry(0.16, 24, 18);
      hairGeo.scale(0.9, 0.95, 1.15);
      const hair = new THREE.Mesh(hairGeo, modelMat);
      hair.position.set(0, 0.08, -0.12);
      headGroup.add(hair);

      // Лебединая шея (плавный конус)
      const neckGeo = new THREE.CylinderGeometry(0.08, 0.105, 0.36, 32);
      const neck = new THREE.Mesh(neckGeo, modelMat);
      neck.position.y = 1.68;
      modelGroup.add(neck);

      // Золотой чокер на шее
      const chokerGeo = new THREE.TorusGeometry(0.098, 0.016, 16, 36);
      const choker = new THREE.Mesh(chokerGeo, goldMat);
      choker.rotation.x = Math.PI / 2;
      choker.position.y = 1.65;
      modelGroup.add(choker);

      modelGroup.add(headGroup);

      // 2. ИЗЯЩНОЕ ИДЕАЛЬНО СГЛАЖЕННОЕ ТОРСО (БЕЗ УГЛОВ И ШВОВ)
      // Используем SplineCurve для непрерывных математических кривых женского тела
      const rawBodyPoints = [
        new THREE.Vector2(0.26, 0.28), // Схождение к бедрам
        new THREE.Vector2(0.35, 0.42), // Нижняя линия бедер
        new THREE.Vector2(0.39, 0.58), // Выраженная линия бедер (Haute Couture silhouette)
        new THREE.Vector2(0.31, 0.74), // Плавный переход
        new THREE.Vector2(0.215, 0.92), // Узкая осиная талия (cinched waist)
        new THREE.Vector2(0.25, 1.04), // Под грудью
        new THREE.Vector2(0.355, 1.18), // Бюст
        new THREE.Vector2(0.35, 1.28), // Верх груди
        new THREE.Vector2(0.31, 1.37), // Ключичная зона
        new THREE.Vector2(0.375, 1.44), // Плечи
        new THREE.Vector2(0.18, 1.50), // Трапеции
        new THREE.Vector2(0.085, 1.54) // Основание шеи
      ];
      const bodySpline = new THREE.SplineCurve(rawBodyPoints);
      const smoothBodyPoints = bodySpline.getPoints(80); // 80 идеально сглаженных точек
      const torsoGeo = new THREE.LatheGeometry(smoothBodyPoints, 64);
      torsoGeo.scale(1.0, 1.0, 0.72);
      torsoGeo.computeVertexNormals();
      const torso = new THREE.Mesh(torsoGeo, modelMat);
      torso.position.y = 0.05;
      modelGroup.add(torso);

      // Золотой пояс на талии
      const waistBeltGeo = new THREE.TorusGeometry(0.23, 0.018, 16, 48);
      waistBeltGeo.scale(1.0, 0.7, 1.0);
      const waistBelt = new THREE.Mesh(waistBeltGeo, goldMat);
      waistBelt.rotation.x = Math.PI / 2;
      waistBelt.position.y = 0.97;
      modelGroup.add(waistBelt);

      // 3. БЕСШОВНЫЕ ИЗЯЩНЫЕ РУКИ (НЕПРЕРЫВНЫЕ 3D СПЛАЙНЫ TUBEGEOMETRY)
      // Больше никаких рубленых цилиндров и щелей!

      // Плечевые гладкие суставы-сферы
      const shoulderGeo = new THREE.SphereGeometry(0.072, 24, 20);
      const leftShoulderMesh = new THREE.Mesh(shoulderGeo, modelMat);
      leftShoulderMesh.position.set(0.36, 1.42, 0);
      modelGroup.add(leftShoulderMesh);

      const rightShoulderMesh = new THREE.Mesh(shoulderGeo, modelMat);
      rightShoulderMesh.position.set(-0.36, 1.42, 0);
      modelGroup.add(rightShoulderMesh);

      // ЛЕВАЯ РУКА: Непрерывная грациозная дуга с кистью на талии (Haute Couture Runway Pose)
      const leftArmPoints = [
        new THREE.Vector3(0.36, 1.42, 0.0),    // Плечо
        new THREE.Vector3(0.47, 1.28, 0.04),   // Бицепс
        new THREE.Vector3(0.53, 1.10, 0.09),   // Локоть (плавный изгиб)
        new THREE.Vector3(0.47, 0.99, 0.16),   // Предплечье
        new THREE.Vector3(0.34, 0.96, 0.20),   // Запястье
        new THREE.Vector3(0.24, 0.95, 0.17),   // Ладонь на талии
        new THREE.Vector3(0.18, 0.94, 0.14)    // Пальцы, аккуратно лежащие на поясе
      ];
      const leftArmCurve = new THREE.CatmullRomCurve3(leftArmPoints);
      leftArmCurve.curveType = 'centripetal';
      const leftArmGeo = new THREE.TubeGeometry(leftArmCurve, 48, 0.045, 18, false);
      const leftArmMesh = new THREE.Mesh(leftArmGeo, modelMat);
      modelGroup.add(leftArmMesh);

      // Золотой браслет на левом запястье (плотно облегает руку)
      const leftBraceletGeo = new THREE.TorusGeometry(0.052, 0.012, 16, 28);
      const leftBracelet = new THREE.Mesh(leftBraceletGeo, goldMat);
      leftBracelet.position.set(0.28, 0.955, 0.19);
      leftBracelet.rotation.y = Math.PI / 4;
      modelGroup.add(leftBracelet);

      // ПРАВАЯ РУКА: Свободно струящаяся подиумная рука вдоль бедра в шаге
      const rightArmPoints = [
        new THREE.Vector3(-0.36, 1.42, 0.0),    // Плечо
        new THREE.Vector3(-0.44, 1.25, -0.03),  // Бицепс
        new THREE.Vector3(-0.46, 1.02, -0.06),  // Локоть
        new THREE.Vector3(-0.42, 0.75, -0.06),  // Предплечье
        new THREE.Vector3(-0.36, 0.48, -0.04),  // Запястье
        new THREE.Vector3(-0.32, 0.28, -0.02),  // Ладонь
        new THREE.Vector3(-0.29, 0.12, 0.00)    // Кончики пальцев в свободном полете
      ];
      const rightArmCurve = new THREE.CatmullRomCurve3(rightArmPoints);
      rightArmCurve.curveType = 'centripetal';
      const rightArmGeo = new THREE.TubeGeometry(rightArmCurve, 48, 0.045, 18, false);
      const rightArmMesh = new THREE.Mesh(rightArmGeo, modelMat);
      modelGroup.add(rightArmMesh);

      // Золотой браслет на правом предплечье
      const rightBraceletGeo = new THREE.TorusGeometry(0.052, 0.012, 16, 28);
      const rightBracelet = new THREE.Mesh(rightBraceletGeo, goldMat);
      rightBracelet.position.set(-0.40, 0.65, -0.05);
      rightBracelet.rotation.x = Math.PI / 8;
      modelGroup.add(rightBracelet);

      // 4. ДЛИННЫЕ СТРОЙНЫЕ НОГИ (НЕПРЕРЫВНЫЕ СПЛАЙНЫ)
      // Правая нога (опорная, прямая)
      const rightLegPoints = [
        new THREE.Vector3(-0.14, 0.35, 0.0),
        new THREE.Vector3(-0.14, -0.15, 0.01),
        new THREE.Vector3(-0.13, -0.65, 0.0),
        new THREE.Vector3(-0.12, -1.15, 0.0),
        new THREE.Vector3(-0.11, -1.65, 0.02)
      ];
      const rightLegCurve = new THREE.CatmullRomCurve3(rightLegPoints);
      const rightLegGeo = new THREE.TubeGeometry(rightLegCurve, 36, 0.075, 18, false);
      const rightLegMesh = new THREE.Mesh(rightLegGeo, modelMat);
      modelGroup.add(rightLegMesh);

      // Туфля на шпильке (правая)
      const shoeGeo = new THREE.ConeGeometry(0.075, 0.22, 18);
      shoeGeo.scale(0.8, 1.0, 1.5);
      const rightShoe = new THREE.Mesh(shoeGeo, goldMat);
      rightShoe.rotation.x = Math.PI / 2.2;
      rightShoe.position.set(-0.11, -1.78, 0.08);
      modelGroup.add(rightShoe);

      const heelGeo = new THREE.CylinderGeometry(0.012, 0.008, 0.25, 12);
      const rightHeel = new THREE.Mesh(heelGeo, goldMat);
      rightHeel.position.set(-0.11, -1.80, -0.03);
      modelGroup.add(rightHeel);

      // Левая нога (подиумный шаг, слегка выдвинута вперед)
      const leftLegPoints = [
        new THREE.Vector3(0.14, 0.35, 0.0),
        new THREE.Vector3(0.14, -0.15, 0.09),
        new THREE.Vector3(0.13, -0.65, 0.18),
        new THREE.Vector3(0.12, -1.15, 0.26),
        new THREE.Vector3(0.11, -1.64, 0.32)
      ];
      const leftLegCurve = new THREE.CatmullRomCurve3(leftLegPoints);
      const leftLegGeo = new THREE.TubeGeometry(leftLegCurve, 36, 0.075, 18, false);
      const leftLegMesh = new THREE.Mesh(leftLegGeo, modelMat);
      modelGroup.add(leftLegMesh);

      const leftShoe = new THREE.Mesh(shoeGeo, goldMat);
      leftShoe.rotation.x = Math.PI / 2.1;
      leftShoe.position.set(0.11, -1.77, 0.40);
      modelGroup.add(leftShoe);

      const leftHeel = new THREE.Mesh(heelGeo, goldMat);
      leftHeel.position.set(0.11, -1.79, 0.28);
      modelGroup.add(leftHeel);

      mainGroup.add(modelGroup);
    } catch (e) {
      console.warn('Fashion model error:', e);
    }
  }

  // ==========================================
  // РАЗВЕВАЮЩАЯСЯ ШЁЛКОВАЯ ЛЕНТА (SILK RIBBON)
  // ==========================================
  function createSilkRibbon(theme) {
    try {
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

      const ribbonCurve = new THREE.CatmullRomCurve3(splinePoints);
      const tubeGeo = new THREE.TubeGeometry(ribbonCurve, 80, 0.034, 12, false);
      const ribbonMat = new THREE.MeshPhysicalMaterial({
        color: theme.accent,
        emissive: theme.accent,
        emissiveIntensity: 0.35,
        roughness: 0.25,
        metalness: 0.65,
        transparent: true,
        opacity: 0.82,
        clearcoat: 1.0
      });
      mainGroup.ribbonMat = ribbonMat;

      ribbonMesh = new THREE.Mesh(tubeGeo, ribbonMat);
      mainGroup.add(ribbonMesh);
    } catch (e) {
      console.warn('Ribbon error:', e);
    }
  }

  // ==========================================
  // ПАРЯЩИЕ КАРТОЧКИ ЛУКБУКА (LOOKBOOK CARDS)
  // ==========================================
  function createLookbookCards(theme, isMobile) {
    try {
      const cardData = [
        { text: '💎 VIP 4K', sub: 'EXCLUSIVE', angle: 0, height: 1.1, radius: isMobile ? 1.45 : 1.85 },
        { text: '✨ GLOCK MODELS', sub: 'AGENCY 2026', angle: Math.PI * 0.55, height: 0.3, radius: isMobile ? 1.5 : 1.95 },
        { text: '🔞 1000+ MEDIA', sub: 'DAILY ARCHIVE', angle: Math.PI * 1.1, height: 1.4, radius: isMobile ? 1.45 : 1.9 },
        { text: '🦋 PRIVATE ACCESS', sub: 'VERIFIED', angle: Math.PI * 1.65, height: -0.4, radius: isMobile ? 1.4 : 1.8 }
      ];

      cardData.forEach((item) => {
        const canvas = document.createElement('canvas');
        canvas.width = 360;
        canvas.height = 130;
        const ctx = canvas.getContext('2d');

        const grad = ctx.createLinearGradient(0, 0, 360, 130);
        grad.addColorStop(0, 'rgba(25, 18, 30, 0.90)');
        grad.addColorStop(1, 'rgba(12, 10, 18, 0.95)');
        ctx.fillStyle = grad;

        drawRoundRect(ctx, 4, 4, 352, 122, 16);
        ctx.fill();

        ctx.strokeStyle = '#f472b6';
        ctx.lineWidth = 4;
        ctx.stroke();

        ctx.font = 'bold 28px sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(item.text, 22, 54);

        ctx.font = '600 15px sans-serif';
        ctx.fillStyle = '#f472b6';
        ctx.fillText(item.sub, 24, 94);

        const texture = new THREE.CanvasTexture(canvas);
        const cardWidth = isMobile ? 0.70 : 0.85;
        const cardHeight = isMobile ? 0.26 : 0.32;
        const cardGeo = new THREE.PlaneGeometry(cardWidth, cardHeight);
        const cardMat = new THREE.MeshBasicMaterial({
          map: texture,
          transparent: true,
          opacity: 0.92,
          side: THREE.DoubleSide
        });

        const cardMesh = new THREE.Mesh(cardGeo, cardMat);
        cardMesh.cardItem = item;
        floatingCards.push(cardMesh);
        mainGroup.add(cardMesh);
      });
    } catch (e) {
      console.warn('Lookbook cards error:', e);
    }
  }

  // ==========================================
  // АТМОСФЕРНАЯ ПЫЛЬЦА (GLITTER PARTICLES)
  // ==========================================
  function createGlitterDust(theme) {
    try {
      const particleCount = 110;
      const geom = new THREE.BufferGeometry();
      const positions = new Float32Array(particleCount * 3);

      for (let i = 0; i < particleCount; i++) {
        const theta = Math.random() * Math.PI * 2;
        const radius = 0.8 + Math.random() * 2.6;
        positions[i * 3] = Math.cos(theta) * radius;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 4.6;
        positions[i * 3 + 2] = Math.sin(theta) * radius;
      }

      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));

      const mat = new THREE.PointsMaterial({
        color: theme.accent,
        size: 0.045,
        transparent: true,
        opacity: 0.75,
        blending: THREE.AdditiveBlending
      });
      mainGroup.dustMat = mat;

      particleDust = new THREE.Points(geom, mat);
      mainGroup.add(particleDust);
    } catch (e) {
      console.warn('Glitter dust error:', e);
    }
  }

  // ==========================================
  // АНИМАЦИЯ И РЕНДЕР-ЦИКЛ
  // ==========================================
  let nextFlashTime = 3.0;

  function animate() {
    requestAnimationFrame(animate);

    const elapsedTime = clock.getElapsedTime();

    mouse.x += (mouse.targetX - mouse.x) * 0.04;
    mouse.y += (mouse.targetY - mouse.y) * 0.04;

    if (mainGroup) {
      mainGroup.rotation.y = Math.sin(elapsedTime * 0.4) * 0.18 + (mouse.x * 0.45);
    }

    if (modelGroup) {
      modelGroup.position.y = -0.15 + Math.sin(elapsedTime * 1.2) * 0.025;
      modelGroup.rotation.z = Math.sin(elapsedTime * 0.6) * 0.018;
    }

    if (ribbonMesh) {
      ribbonMesh.rotation.y = -elapsedTime * 0.25;
      ribbonMesh.position.y = Math.sin(elapsedTime * 0.9) * 0.04;
    }

    floatingCards.forEach((card, i) => {
      const item = card.cardItem;
      const curAngle = item.angle + (elapsedTime * 0.22);
      const r = item.radius;
      card.position.x = Math.cos(curAngle) * r;
      card.position.z = Math.sin(curAngle) * r;
      card.position.y = item.height + Math.sin(elapsedTime * 1.5 + i) * 0.08;
      if (camera) card.lookAt(camera.position);
    });

    if (particleDust) {
      particleDust.rotation.y = elapsedTime * 0.05;
    }

    if (elapsedTime > nextFlashTime) {
      triggerPaparazziFlash();
      nextFlashTime = elapsedTime + 2.5 + Math.random() * 4.0;
    }
    if (paparazziFlash && paparazziFlash.intensity > 0) {
      paparazziFlash.intensity *= 0.88;
      if (paparazziFlash.intensity < 0.05) paparazziFlash.intensity = 0;
    }

    if (renderer && scene && camera) {
      renderer.render(scene, camera);
    }
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
    const width = window.innerWidth;
    const height = window.innerHeight;
    const isMobile = width < 768;

    if (camera) {
      camera.aspect = width / height;
      camera.position.z = isMobile ? 7.6 : (width < 1024 ? 6.4 : 5.6);
      camera.position.y = isMobile ? 0.05 : 0.25;
      camera.updateProjectionMatrix();
    }
    if (renderer) {
      renderer.setSize(width, height);
    }
    applyResponsiveLayout(width);
  }

  function onScroll() {
    const scrollY = window.pageYOffset || document.documentElement.scrollTop;
    if (mainGroup) {
      const isMobile = window.innerWidth < 768;
      const baseScale = isMobile ? 0.74 : (window.innerWidth < 1200 ? 0.9 : 1.0);
      const scrollProgress = Math.min(scrollY / 700, 1);
      mainGroup.scale.setScalar(baseScale * (1.0 - scrollProgress * 0.22));
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

      if (mainGroup && mainGroup.ribbonMat) {
        gsap.to(mainGroup.ribbonMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
        gsap.to(mainGroup.ribbonMat.emissive, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }

      if (catwalkGroup && catwalkGroup.podiumRingMat) {
        gsap.to(catwalkGroup.podiumRingMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }
      if (catwalkGroup && catwalkGroup.haloMat) {
        gsap.to(catwalkGroup.haloMat.color, { r: ((t.accent >> 16) & 255) / 255, g: ((t.accent >> 8) & 255) / 255, b: (t.accent & 255) / 255, duration: 0.8 });
      }
      if (mainGroup && mainGroup.dustMat) {
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
