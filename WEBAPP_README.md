# Botshop Web App (Mini App)

Полнофункциональное веб-приложение для покупок товаров прямо в Telegram!

## 🚀 Возможности

✅ **Каталог товаров** - красивый интерфейс для просмотра  
✅ **Фильтрация по категориям** - быстрая навигация  
✅ **Модальное окно** - подробная информация о товаре  
✅ **Покупка товаров** - интеграция с Telegram Bot API  
✅ **Адаптивный дизайн** - оптимально смотрится на мобильных  
✅ **Темное оформление** - красивый интерфейс в стиле Telegram  

## 📁 Структура

```
webapp.html          - Основной файл Web App
webapp_server.py     - Локальный тестовый сервер
handlers/webapp.py   - Обработчик данных из Web App в боте
```

## 🔧 Установка

### Локальное тестирование

1. Запустите тестовый сервер:
```bash
python webapp_server.py
```

2. Откройте в браузере:
```
http://localhost:8000/webapp.html
```

### Развертывание на GitHub Pages

1. Создайте репозиторий `botshop-webapp`
2. Включите GitHub Pages в настройках репозитория
3. Загрузите `webapp.html` в корень репозитория
4. Откройте по адресу: `https://username.github.io/botshop-webapp/`

### Использование в боте

Ссылка на Web App в `keyboards.py`:
```python
[InlineKeyboardButton(text="🛍️ Открыть Web App", web_app={"url": "https://username.github.io/botshop-webapp/"})]
```

## 📱 API Интеграция

Web App отправляет данные в бот через `web_app_data`. 

Пример отправляемых данных:
```json
{
  "action": "buy",
  "product_id": 1,
  "product_name": "Товар 1",
  "price": 2999
}
```

Обработчик находится в `handlers/webapp.py`.

## 🎨 Дизайн

- **Цветовая схема**: Фиолетово-синий градиент (#667eea → #764ba2)
- **Фон**: Темный (#1a1a1a)
- **Текст**: Светлый (#fff)
- **Шрифт**: Системные шрифты (SF Pro Display на iOS, Roboto на Android)

## 📚 Технологии

- Vanilla JavaScript (без фреймворков)
- HTML5 Semantic
- CSS3 Grid & Flexbox
- Telegram Web App SDK

## 🔐 Безопасность

- Все данные идут через Telegram (защищено)
- Web App работает в защищенном контексте Telegram
- Проверка `web_app_data` на сервере необязательна, но рекомендуется

## 📈 Дальнейшее развитие

- [ ] Реальная загрузка товаров из API
- [ ] Корзина с накоплением товаров
- [ ] История покупок
- [ ] Рекомендации товаров
- [ ] Поиск по товарам
- [ ] Галерея фотографий товаров
- [ ] Оценка и отзывы

## 💡 Примеры использования

### Получение данных пользователя
```javascript
const user = TelegramWebApp.initData;
const userId = TelegramWebApp.initDataUnsafe.user.id;
```

### Отправка данных в бот
```javascript
TelegramWebApp.sendData(JSON.stringify({
    action: 'buy',
    product_id: 123
}));
```

### Показ уведомления
```javascript
TelegramWebApp.showAlert('Товар добавлен в корзину!');
TelegramWebApp.showConfirm('Вы уверены?');
TelegramWebApp.showPopup({});
```

## 📞 Поддержка

Для вопросов или багов создавайте issues в репозитории проекта.

---

**Автор**: Botshop Team  
**Версия**: 1.0.0  
**Лицензия**: MIT
