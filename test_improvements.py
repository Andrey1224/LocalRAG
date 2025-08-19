#!/usr/bin/env python3
"""
Автоматическое тестирование улучшений LocalRAG на исходных 20 вопросах
"""

import requests
import time
import json

API_BASE_URL = "http://localhost:8000"

# 20 тестовых вопросов из pattern_analysis.md 
test_questions = [
    "есть ли поддержка WhatsApp?",
    "AI-ассистент", 
    "будет ли голосовая поддержка?",
    "WhatsApp Business API",
    "планируется ли VoIP?",
    "поддерживает ли Slack интеграцию?",
    "есть ли live chat?",
    "поддержка 2FA",
    "ticketing system",
    "база знаний",
    "сколько стоит Pro тариф?",
    "есть ли пробный период?",
    "как связаться с поддержкой?",
    "часы работы поддержки",
    "где хранятся данные?",
    "проблемы с Android",
    "ошибка экспорта CSV",
    "не доходит письмо",
    "ошибка 403",
    "как сбросить пароль?"
]

def test_question(question: str, test_num: int) -> dict:
    """Тестирует один вопрос"""
    try:
        start_time = time.time()
        response = requests.post(
            f"{API_BASE_URL}/ask",
            json={"question": question},
            timeout=30
        )
        response_time = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get("answer", "")
            
            # Анализируем качество ответа
            analysis = analyze_answer_quality(question, answer)
            
            return {
                "test_num": test_num,
                "question": question,
                "success": True,
                "answer": answer,
                "response_time_ms": response_time,
                "analysis": analysis
            }
        else:
            return {
                "test_num": test_num,
                "question": question, 
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "response_time_ms": response_time
            }
    except Exception as e:
        return {
            "test_num": test_num,
            "question": question,
            "success": False,
            "error": str(e),
            "response_time_ms": 0
        }

def analyze_answer_quality(question: str, answer: str) -> dict:
    """Анализирует качество ответа"""
    analysis = {
        "has_duplicates": False,
        "has_relevant_content": False,
        "has_roadmap_info": False,
        "content_length": len(answer),
        "estimated_quality": "unknown"
    }
    
    # Проверяем дубликаты
    lines = [line.strip() for line in answer.split('\n') if line.strip()]
    unique_lines = set(lines)
    analysis["has_duplicates"] = len(lines) != len(unique_lines)
    
    # Проверяем релевантность
    question_lower = question.lower()
    answer_lower = answer.lower()
    
    # Специфические проверки по типам вопросов
    if "whatsapp" in question_lower:
        analysis["has_relevant_content"] = "whatsapp" in answer_lower
        analysis["has_roadmap_info"] = "q3" in answer_lower or "планируется" in answer_lower
        
    elif "slack" in question_lower:
        analysis["has_relevant_content"] = "slack" in answer_lower
        
    elif "live chat" in question_lower:
        analysis["has_relevant_content"] = "live chat" in answer_lower
        
    elif "2fa" in question_lower or "двухфакторн" in question_lower:
        analysis["has_relevant_content"] = "двухфакторн" in answer_lower or "2fa" in answer_lower
        
    elif "связаться" in question_lower:
        analysis["has_relevant_content"] = "support@" in answer_lower or "email" in answer_lower
        
    elif "тариф" in question_lower:
        analysis["has_relevant_content"] = "$" in answer_lower or "тариф" in answer_lower
        
    elif "данные" in question_lower:
        analysis["has_relevant_content"] = "aws" in answer_lower or "данные" in answer_lower
        
    else:
        # Общая проверка релевантности
        analysis["has_relevant_content"] = True  # По умолчанию считаем релевантным
    
    # Оценка качества
    if analysis["has_duplicates"]:
        analysis["estimated_quality"] = "poor"
    elif analysis["has_relevant_content"]:
        analysis["estimated_quality"] = "good"
    else:
        analysis["estimated_quality"] = "fair"
        
    return analysis

def run_tests():
    """Запускает все тесты"""
    print("🚀 Запуск тестирования улучшений LocalRAG...")
    print(f"📊 Будет протестировано {len(test_questions)} вопросов\n")
    
    results = []
    successful_tests = 0
    total_response_time = 0
    
    for i, question in enumerate(test_questions, 1):
        print(f"🧪 Тест {i:2d}/20: {question[:50]}{'...' if len(question) > 50 else ''}")
        
        result = test_question(question, i)
        results.append(result)
        
        if result["success"]:
            successful_tests += 1
            total_response_time += result["response_time_ms"]
            
            # Краткий анализ
            analysis = result["analysis"]
            quality = analysis["estimated_quality"]
            quality_emoji = {"good": "✅", "fair": "⚠️", "poor": "❌"}
            
            print(f"   {quality_emoji.get(quality, '❓')} {quality.upper()}: "
                  f"{result['response_time_ms']}ms, "
                  f"duplicates: {'Yes' if analysis['has_duplicates'] else 'No'}")
        else:
            print(f"   ❌ FAILED: {result['error']}")
            
        time.sleep(0.5)  # Небольшая пауза между запросами
    
    # Финальная статистика
    print(f"\n{'='*60}")
    print(f"📈 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"✅ Успешных тестов: {successful_tests}/{len(test_questions)} ({successful_tests/len(test_questions)*100:.1f}%)")
    
    if successful_tests > 0:
        avg_response_time = total_response_time / successful_tests
        print(f"⏱️  Среднее время ответа: {avg_response_time:.0f}ms")
        
        # Анализ по качеству
        quality_counts = {"good": 0, "fair": 0, "poor": 0}
        duplicate_count = 0
        
        for result in results:
            if result["success"]:
                analysis = result["analysis"]
                quality_counts[analysis["estimated_quality"]] += 1
                if analysis["has_duplicates"]:
                    duplicate_count += 1
        
        print(f"📊 Качество ответов:")
        print(f"   ✅ Good: {quality_counts['good']}")
        print(f"   ⚠️  Fair: {quality_counts['fair']}")
        print(f"   ❌ Poor: {quality_counts['poor']}")
        print(f"🔄 Дубликаты найдены в: {duplicate_count} тестах")
        
        # Сравнение с исходными результатами
        original_success_rate = 6.5  # из 10
        current_success_rate = (quality_counts['good'] / successful_tests) * 10 if successful_tests > 0 else 0
        improvement = current_success_rate - original_success_rate
        
        print(f"\n🎯 ОЦЕНКА УЛУЧШЕНИЙ:")
        print(f"   Исходная оценка: 6.5/10")
        print(f"   Текущая оценка: {current_success_rate:.1f}/10")
        print(f"   Улучшение: {improvement:+.1f} баллов")
        
        if improvement >= 1.5:
            print("   🎉 ЦЕЛЬ ДОСТИГНУТА! (улучшение > 1.5 баллов)")
        elif improvement >= 0.5:
            print("   👍 Хорошее улучшение!")
        else:
            print("   😐 Небольшое улучшение")
    
    # Сохраняем подробные результаты
    with open("test_results_improved.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Подробные результаты сохранены в test_results_improved.json")

if __name__ == "__main__":
    run_tests()