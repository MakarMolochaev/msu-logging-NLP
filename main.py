import json
import pika
import grpc
from concurrent import futures
import msu_logging_pb2
import msu_logging_pb2_grpc
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import login

# Загружаем модель и токенизатор
model_name = "google/gemma-3-1b-it"
tokenizer = 0
model = 0

def MakeProtocol(transcribed_text):
    # Читаем текст из входного файла
    print("making prompt")
    # Формируем промпт
    prompt = (
        "Анализируй предоставленный текст онлайн-созвона и преобразуй его в официальный протокол встречи. "
        "Сохраняй все ключевые решения и поручения. Структура:\n\n"
        "1. **Общая информация**\n"
        "   - Дата и время встречи\n"
        "   - Участники (отметь отсутствующих)\n"
        "   - Основная тема\n\n"
        "2. **Обсужденные вопросы** (оформи как подзаголовки)\n"
        "   - По каждому вопросу выделяй: \n"
        "     * Проблему/тему\n"
        "     * Озвученные позиции\n"
        "     * Принятые решения\n"
        "     * Ответственных и сроки\n\n"
        "3. **Поручения**\n"
        "   - Четкий список (Кто? Что? До какого срока?)\n"
        "   - Отметь 'на контроль' если важно\n\n"
        "4. **Дополнительные заметки**\n"
        "   - Спорные моменты\n"
        "   - Вопросы для следующих встреч\n\n"
        f"Текст звонка:\n{transcribed_text}\n\n"
    )

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024).to(model.device)
    input_length = inputs.input_ids.shape[1]  # Запоминаем длину промпта в токенах

    print("generating answer")
    # Генерируем ответ
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=1500)

    print("decoding")

    # Декодируем только сгенерированную часть (исключая промпт)
    output_text = tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True)

    print("answer has been generated")
    return output_text

class RabbitMQConsumer:
    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.URLParameters('amqp://admin:admin@localhost:5672/')
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue='process_queue', durable=True)
        
        self.grpc_channel = grpc.insecure_channel(
        'localhost:50051',
        options=[
            ('grpc.connect_timeout_ms', 5000),  # 5 секунд на подключение
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
        ]
        )
        self.grpc_stub = msu_logging_pb2_grpc.ProtocolStub(self.grpc_channel)

    def callback(self, ch, method, properties, body):
        try:
            message = json.loads(body)
            task_id = message['TaskId']
            transcribed_text = message['TranscribedText']
            
            print(f"Received task: {task_id}, transcribed text: {transcribed_text}")
            
            protocol = MakeProtocol(transcribed_text)
            
            grpc_response = self.grpc_stub.SendProtocolResult(
                msu_logging_pb2.ProtocolResult(
                    success=True,
                    errorMessage="",
                    result=protocol,
                    taskId=task_id
                )
            )
            
            print(f"gRPC response: {grpc_response}")
            ch.basic_ack(delivery_tag=method.delivery_tag)  # Подтверждаем после успеха
            
        except Exception as e:
            print(f"Error processing message: {e}")

    def start_consuming(self):
        self.channel.basic_consume(
            queue='process_queue',
            on_message_callback=self.callback,
            auto_ack=False
        )
        print('Waiting for messages. To exit press CTRL+C')
        self.channel.start_consuming()

if __name__ == '__main__':
    print('loading model')
    login(open('token.txt').read())
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name)
    print("model loaded")
    try:
        consumer = RabbitMQConsumer()
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("Consumer stopped by user")
    except Exception as e:
        print(f"Error: {e}")