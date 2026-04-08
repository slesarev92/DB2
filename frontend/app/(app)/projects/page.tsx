/**
 * /projects — список проектов.
 *
 * MVP заглушка для задачи 3.1 (только проверка что защищённый маршрут
 * работает после login). Полная реализация — задача 3.2:
 *   - GET /api/projects → карточки с NPV/Go-NoGo
 *   - кнопка "Создать проект" → /projects/new
 */
export default function ProjectsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Проекты</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Список будет реализован в задаче 3.2 (создание/редактирование/
          KPI карточки).
        </p>
      </div>

      <div className="rounded-md border bg-card p-6 text-card-foreground">
        <p className="text-sm">
          Заглушка задачи 3.1. Auth flow работает: вы видите эту страницу,
          значит залогинились успешно. Токен сохранён в localStorage,
          текущий user отображается в sidebar внизу слева.
        </p>
      </div>
    </div>
  );
}
