"""
Сценарии нагрузочного тестирования для Todo List приложения

Два типа пользователей:
1. ReaderUser - пользователь, который в основном читает данные
2. WriterUser - пользователь, который создает, обновляет и удаляет данные
"""

from locust import HttpUser, task, between
import random


class ReaderUser(HttpUser):
    """
    Пользователь-читатель: выполняет операции чтения данных
    Задачи:
    1. Проверка здоровья сервиса
    2. Получение информации об инстансе
    3. Просмотр списка todos
    4. Просмотр списка todos с фильтрацией (повторный запрос)
    5. Получение информации об инстансе (повторно)
    """
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Инициализация пользователя"""
        self.todo_ids = []
    
    @task(3)
    def check_health(self):
        """Задача 1: Проверка здоровья сервиса"""
        with self.client.get("/health", catch_response=True, name="Health Check") as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed with status {response.status_code}")
    
    @task(3)
    def get_instance_info(self):
        """Задача 2: Получение информации об инстансе"""
        with self.client.get("/api/info", catch_response=True, name="Get Instance Info") as response:
            if response.status_code == 200:
                data = response.json()
                response.success()
            else:
                response.failure(f"Get info failed with status {response.status_code}")
    
    @task(5)
    def get_all_todos(self):
        """Задача 3: Просмотр списка todos"""
        with self.client.get("/api/todos", catch_response=True, name="Get All Todos") as response:
            if response.status_code == 200:
                data = response.json()
                if 'todos' in data:
                    self.todo_ids = [todo['id'] for todo in data['todos']]
                response.success()
            else:
                response.failure(f"Get todos failed with status {response.status_code}")
    
    @task(2)
    def get_todos_again(self):
        """Задача 4: Повторный просмотр списка todos"""
        with self.client.get("/api/todos", catch_response=True, name="Get Todos Again") as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get todos again failed with status {response.status_code}")
    
    @task(2)
    def refresh_instance_info(self):
        """Задача 5: Обновление информации об инстансе"""
        with self.client.get("/api/info", catch_response=True, name="Refresh Instance Info") as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Refresh info failed with status {response.status_code}")


class WriterUser(HttpUser):
    """
    Пользователь-писатель: выполняет операции создания, обновления и удаления данных
    Задачи:
    1. Создание нового todo
    2. Просмотр списка todos
    3. Обновление существующего todo
    4. Создание еще одного todo
    5. Удаление todo
    """
    
    wait_time = between(2, 5)
    
    def on_start(self):
        """Инициализация пользователя"""
        self.created_todo_ids = []
        self.all_todo_ids = []
    
    @task(4)
    def create_todo(self):
        """Задача 1: Создание нового todo"""
        todo_titles = [
            "Купить продукты",
            "Изучить Python",
            "Написать отчет",
            "Позвонить другу",
            "Сделать зарядку",
            "Прочитать книгу",
            "Подготовить презентацию",
            "Встретиться с командой"
        ]
        todo_descriptions = [
            "Молоко, хлеб, яйца",
            "Изучить асинхронное программирование",
            "Отчет по нагрузочному тестированию",
            "Обсудить планы на выходные",
            "Утренняя зарядка 30 минут",
            "Глава 5 из книги по алгоритмам",
            "Слайды для завтрашней встречи",
            "Обсудить новый проект"
        ]
        
        title = random.choice(todo_titles)
        description = random.choice(todo_descriptions)
        
        payload = {
            "title": title,
            "description": description
        }
        
        with self.client.post(
            "/api/todos",
            json=payload,
            catch_response=True,
            name="Create Todo"
        ) as response:
            if response.status_code == 201:
                data = response.json()
                if 'id' in data:
                    self.created_todo_ids.append(data['id'])
                response.success()
            else:
                response.failure(f"Create todo failed with status {response.status_code}")
    
    @task(3)
    def get_all_todos(self):
        """Задача 2: Просмотр списка todos"""
        with self.client.get("/api/todos", catch_response=True, name="Get All Todos") as response:
            if response.status_code == 200:
                data = response.json()
                if 'todos' in data:
                    self.all_todo_ids = [todo['id'] for todo in data['todos']]
                response.success()
            else:
                response.failure(f"Get todos failed with status {response.status_code}")
    
    @task(3)
    def update_todo(self):
        """Задача 3: Обновление существующего todo"""
        if not self.all_todo_ids:
            with self.client.get("/api/todos", catch_response=True) as response:
                if response.status_code == 200:
                    data = response.json()
                    if 'todos' in data and len(data['todos']) > 0:
                        self.all_todo_ids = [todo['id'] for todo in data['todos']]
        
        if self.all_todo_ids:
            todo_id = random.choice(self.all_todo_ids)
            update_data = {
                "completed": random.choice([True, False]),
                "title": f"Обновленная задача {random.randint(1, 100)}"
            }
            
            with self.client.put(
                f"/api/todos/{todo_id}",
                json=update_data,
                catch_response=True,
                name="Update Todo"
            ) as response:
                if response.status_code == 200:
                    response.success()
                elif response.status_code == 404:
                    if todo_id in self.all_todo_ids:
                        self.all_todo_ids.remove(todo_id)
                    response.success()
                else:
                    response.failure(f"Update todo failed with status {response.status_code}")
    
    @task(2)
    def create_another_todo(self):
        """Задача 4: Создание еще одного todo"""
        todo_titles = [
            "Завершить проект",
            "Отправить письмо",
            "Обновить документацию",
            "Проверить код",
            "Настроить CI/CD"
        ]
        
        payload = {
            "title": random.choice(todo_titles),
            "description": "Дополнительная задача"
        }
        
        with self.client.post(
            "/api/todos",
            json=payload,
            catch_response=True,
            name="Create Another Todo"
        ) as response:
            if response.status_code == 201:
                data = response.json()
                if 'id' in data:
                    self.created_todo_ids.append(data['id'])
                response.success()
            else:
                response.failure(f"Create another todo failed with status {response.status_code}")
    
    @task(2)
    def delete_todo(self):
        """Задача 5: Удаление todo"""
        if not self.all_todo_ids:
            with self.client.get("/api/todos", catch_response=True) as response:
                if response.status_code == 200:
                    data = response.json()
                    if 'todos' in data and len(data['todos']) > 0:
                        self.all_todo_ids = [todo['id'] for todo in data['todos']]
        
        if self.all_todo_ids:
            todo_id = random.choice(self.all_todo_ids)
            
            with self.client.delete(
                f"/api/todos/{todo_id}",
                catch_response=True,
                name="Delete Todo"
            ) as response:
                if response.status_code == 200:
                    if todo_id in self.all_todo_ids:
                        self.all_todo_ids.remove(todo_id)
                    if todo_id in self.created_todo_ids:
                        self.created_todo_ids.remove(todo_id)
                    response.success()
                elif response.status_code == 404:
                    if todo_id in self.all_todo_ids:
                        self.all_todo_ids.remove(todo_id)
                    response.success()
                else:
                    response.failure(f"Delete todo failed with status {response.status_code}")
