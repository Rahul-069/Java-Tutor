import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers import TextIteratorStreamer
from threading import Thread
import random
import uuid
import json
import re
from datetime import datetime

class JavaTutorModel:
    def __init__(self):
        print("Loading DeepSeek Coder model...")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            "deepseek-ai/deepseek-coder-1.3b-instruct",
            trust_remote_code=True
        )
        
        # Fix padding token warning
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        
        # OPTIMIZATION: Load model with 8-bit quantization (2-3x faster!)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        if self.device == "cuda":
            print("Loading model with 8-bit quantization for faster inference...")
            # Use 8-bit quantization - much faster!
            self.model = AutoModelForCausalLM.from_pretrained(
                "deepseek-ai/deepseek-coder-1.3b-instruct",
                trust_remote_code=True,
                device_map="auto",
                load_in_8bit=True,  # 8-bit quantization
                torch_dtype=torch.float16,
                attn_implementation="flash_attention_2"  # Flash Attention 2 for 2x speed
            )
        else:
            # CPU fallback
            self.model = AutoModelForCausalLM.from_pretrained(
                "deepseek-ai/deepseek-coder-1.3b-instruct",
                trust_remote_code=True,
                torch_dtype=torch.bfloat16
            )
            self.model = self.model.to(self.device)
        
        print(f"Model loaded on {self.device} with optimizations")
        
        # Active quizzes storage
        self.active_quizzes = {}
        
        # Java topics for quiz generation
        self.quiz_topics = {
            'overall': 'general Java programming concepts',
            'basics': 'Java basics including variables, data types, loops, arrays, and control structures',
            'oop': 'Object-Oriented Programming concepts like classes, objects, inheritance, polymorphism, encapsulation, and abstraction',
            'advanced': 'Advanced Java topics including collections, exceptions, threads, generics, and lambda expressions',
            'frameworks': 'Java frameworks like Spring, Hibernate, Maven, and JUnit'
        }
        
        # Fallback questions database (used if AI generation fails)
        self.fallback_questions = {
            'basics': [
                {
                    'question': 'Which of the following is NOT a primitive data type in Java?',
                    'options': ['int', 'String', 'boolean', 'char'],
                    'correct': 1,
                    'explanation': 'String is a class in Java, not a primitive data type. The primitive data types are byte, short, int, long, float, double, boolean, and char.'
                },
                {
                    'question': 'What is the default value of an int variable in Java?',
                    'options': ['null', '0', '1', 'undefined'],
                    'correct': 1,
                    'explanation': 'The default value of an int variable in Java is 0.'
                },
                {
                    'question': 'Which loop is guaranteed to execute at least once?',
                    'options': ['for loop', 'while loop', 'do-while loop', 'enhanced for loop'],
                    'correct': 2,
                    'explanation': 'The do-while loop checks the condition after executing the body, so it always executes at least once.'
                }
            ],
            'oop': [
                {
                    'question': 'What is encapsulation in Java?',
                    'options': ['Creating multiple classes', 'Hiding implementation details', 'Creating objects', 'Inheriting properties'],
                    'correct': 1,
                    'explanation': 'Encapsulation is the concept of hiding the internal implementation details and exposing only necessary information through public methods.'
                },
                {
                    'question': 'Which keyword is used to inherit a class in Java?',
                    'options': ['implements', 'extends', 'inherits', 'super'],
                    'correct': 1,
                    'explanation': 'The extends keyword is used to inherit a class in Java.'
                },
                {
                    'question': 'What is method overriding?',
                    'options': ['Creating multiple methods with same name', 'Redefining a method in subclass', 'Calling parent method', 'Creating abstract methods'],
                    'correct': 1,
                    'explanation': 'Method overriding is when a subclass provides a specific implementation of a method already defined in its parent class.'
                }
            ],
            'advanced': [
                {
                    'question': 'Which exception is thrown when dividing by zero?',
                    'options': ['NullPointerException', 'ArithmeticException', 'NumberFormatException', 'ArrayIndexOutOfBoundsException'],
                    'correct': 1,
                    'explanation': 'ArithmeticException is thrown when an exceptional arithmetic condition occurs, such as dividing by zero.'
                },
                {
                    'question': 'What is the difference between ArrayList and LinkedList?',
                    'options': ['No difference', 'ArrayList is faster for random access', 'LinkedList is always better', 'ArrayList cannot store objects'],
                    'correct': 1,
                    'explanation': 'ArrayList is faster for random access operations, while LinkedList is better for frequent insertions and deletions.'
                },
                {
                    'question': 'Which collection does not allow duplicate elements?',
                    'options': ['List', 'Set', 'Queue', 'Map'],
                    'correct': 1,
                    'explanation': 'Set is a collection that does not allow duplicate elements.'
                }
            ],
            'frameworks': [
                {
                    'question': 'What is Spring Framework primarily used for?',
                    'options': ['GUI development', 'Dependency injection and IoC', 'Database management', 'File handling'],
                    'correct': 1,
                    'explanation': 'Spring Framework is primarily used for dependency injection and Inversion of Control (IoC).'
                },
                {
                    'question': 'What is Maven?',
                    'options': ['IDE', 'Build tool', 'Database', 'Web server'],
                    'correct': 1,
                    'explanation': 'Maven is a build automation and project management tool used primarily for Java projects.'
                },
                {
                    'question': 'What is JUnit used for?',
                    'options': ['Building applications', 'Unit testing', 'Database operations', 'Web development'],
                    'correct': 1,
                    'explanation': 'JUnit is a testing framework used for unit testing Java applications.'
                }
            ]
        }
        
        # Warm up model
        self._warmup()
    
    def _warmup(self):
        """Warm up the model with a dummy request"""
        print("Warming up model...")
        print("Model ready!")
    
    def detect_other_language(self, text):
        """Detect if user is asking about non-Java programming language"""
        text_lower = text.lower()
        
        other_langs = {
            'python': ['python', 'py', 'django', 'flask', 'pandas'],
            'javascript': ['javascript', 'js', 'node', 'react', 'vue'],
            'c++': ['c++', 'cpp'],
            'c#': ['c#', 'csharp', '.net'],
            'php': ['php', 'laravel'],
            'ruby': ['ruby', 'rails'],
            'go': ['golang', 'go lang'],
        }
        
        for lang, keywords in other_langs.items():
            if any(keyword in text_lower for keyword in keywords):
                return lang
        
        return None
    
    def generate_response_stream_with_stop(self, user_input, history=[], stop_flag=None):
        """Generate AI response with streaming and stop capability"""
        
        # Check if asking about other languages
        other_lang = self.detect_other_language(user_input)
        if other_lang:
            error_msg = f"""I appreciate your question about {other_lang.title()}! However, I'm specifically designed as a Java tutor.

I can help you with:
✅ Java fundamentals (variables, loops, conditionals)
✅ Object-Oriented Programming in Java
✅ Java collections and data structures
✅ Exception handling
✅ Java frameworks (Spring, Hibernate)

Please ask me any Java-related questions!"""
            yield error_msg
            return
        
        # System prompt
        system_prompt = """You are JavaTutor, an expert Java programming instructor. 

Your role:
- Answer ONLY Java programming questions
- Provide clear, concise explanations
- Include code examples when helpful
- Be encouraging and supportive
- Keep responses under 200 words unless asked for details."""
        
        # Build conversation
        messages = [{'role': 'system', 'content': system_prompt}]
        
        # Add conversation history
        for exchange in history[-3:]:
            if len(exchange) == 2:
                messages.append({'role': 'user', 'content': exchange[0]})
                messages.append({'role': 'assistant', 'content': exchange[1]})
        
        # Add current user message
        messages.append({'role': 'user', 'content': user_input})
        
        try:
            # Prepare inputs
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt"
            ).to(self.device)
            
            attention_mask = torch.ones_like(inputs)
            
            # Use streamer
            
            streamer = TextIteratorStreamer(
                self.tokenizer,
                skip_prompt=True,
                skip_special_tokens=True
            )
            
            generation_kwargs = dict(
                inputs=inputs,
                attention_mask=attention_mask,
                streamer=streamer,
                max_new_tokens=512,
                do_sample=True,
                top_k=40,
                top_p=0.9,
                temperature=0.7,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
            
            # Start generation thread
            thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
            thread.start()
            
            # Stream tokens
            for new_text in streamer:
                # Check stop flag
                if stop_flag and stop_flag.get('should_stop', False):
                    break
                
                yield new_text
            
            thread.join()
            
        except Exception as e:
            yield f"Error: {str(e)}"
    
    def generate_quiz_questions(self, topic, num_questions):
        """Generate quiz questions dynamically using AI"""
        topic_key = topic.lower()
        topic_description = self.quiz_topics.get(topic_key, self.quiz_topics['overall'])
        
        system_prompt = f"""You are a Java programming quiz generator. Generate EXACTLY {num_questions} multiple choice questions about {topic_description}.

CRITICAL FORMATTING RULES:
1. Return ONLY valid JSON, no extra text or markdown
2. Each question must have exactly 4 options
3. The correct answer index must be 0, 1, 2, or 3
4. Provide clear explanations

Format (STRICT JSON):
{{
  "questions": [
    {{
      "question": "Question text here?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct": 1,
      "explanation": "Explanation here."
    }}
  ]
}}"""

        user_prompt = f"Generate {num_questions} multiple choice questions about {topic_description}. Return ONLY the JSON object, nothing else."
        
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]
        
        try:
            print(f"Generating {num_questions} quiz questions for topic: {topic}")
            
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt"
            ).to(self.device)
            
            attention_mask = torch.ones_like(inputs)
            
            outputs = self.model.generate(
                inputs,
                attention_mask=attention_mask,
                max_new_tokens=1500,  # More tokens for multiple questions
                do_sample=True,
                top_k=40,
                top_p=0.9,
                temperature=0.7,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
            
            response = self.tokenizer.decode(
                outputs[0][len(inputs[0]):],
                skip_special_tokens=True
            ).strip()
            
            print("Raw AI response:", response[:200])
            
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*"questions"[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)
                quiz_data = json.loads(json_str)
                
                if 'questions' in quiz_data and len(quiz_data['questions']) > 0:
                    print(f"✅ Successfully generated {len(quiz_data['questions'])} AI questions")
                    return quiz_data['questions'][:num_questions]
            
            print("⚠️ Failed to parse AI response, using fallback questions")
            return self._get_fallback_questions(topic_key, num_questions)
            
        except Exception as e:
            print(f"❌ Error generating quiz: {str(e)}")
            return self._get_fallback_questions(topic_key, num_questions)
    
    def _get_fallback_questions(self, topic, num_questions):
        """Fallback questions if AI generation fails"""
        print(f"📚 Using fallback questions for topic: {topic}")
        
        # Get questions for topic, default to basics if not found
        available = self.fallback_questions.get(topic, self.fallback_questions['basics'])
        
        # Return random selection
        return random.sample(available, min(num_questions, len(available)))
    
    def start_quiz(self, topic, num_questions):
        """Start a new quiz with AI-generated questions"""
        topic_key = topic.lower()
        
        # Generate questions using AI
        print(f"🎯 Starting quiz: {topic} with {num_questions} questions")
        # questions = self.generate_quiz_questions(topic, num_questions)
        
        # if not questions or len(questions) == 0:
        #     print("⚠️ No questions generated, using fallback")
        #     questions = self._get_fallback_questions(topic_key, num_questions)

        questions = self._get_fallback_questions(topic_key, num_questions)

        # Create quiz
        quiz_id = str(uuid.uuid4())
        quiz_data = {
            'quiz_id': quiz_id,
            'topic': topic,
            'questions': questions,
            'current_index': 0,
            'score': 0,
            'answers': [],
            'start_time': datetime.now().isoformat()
        }
        
        self.active_quizzes[quiz_id] = quiz_data
        
        # Return first question
        return {
            'quiz_id': quiz_id,
            'topic': topic,
            'total_questions': len(questions),
            'current_question': self._format_question(questions[0], 0, len(questions))
        }
    
    def _format_question(self, question_data, index, total):
        """Format question for API response"""
        return {
            'question_number': index + 1,
            'total_questions': total,
            'question': question_data['question'],
            'options': question_data['options']
        }
    
    def submit_answer(self, quiz_id, question_index, selected_option):
        """Submit an answer and get feedback"""
        if quiz_id not in self.active_quizzes:
            return {'error': 'Quiz not found'}
        
        quiz = self.active_quizzes[quiz_id]
        questions = quiz['questions']
        
        if question_index >= len(questions):
            return {'error': 'Invalid question index'}
        
        current_q = questions[question_index]
        is_correct = selected_option == current_q['correct']
        
        # Record answer
        quiz['answers'].append({
            'question_index': question_index,
            'selected': selected_option,
            'correct': current_q['correct'],
            'is_correct': is_correct
        })
        
        if is_correct:
            quiz['score'] += 1
        
        # Check if quiz complete
        is_complete = question_index >= len(questions) - 1
        
        response = {
            'is_correct': is_correct,
            'explanation': current_q['explanation'],
            'correct_option': current_q['correct'],
            'is_complete': is_complete,
            'topic': quiz['topic']
        }
        
        if is_complete:
            # Quiz finished
            score = quiz['score']
            total = len(questions)
            percentage = (score / total) * 100
            
            response['final_results'] = {
                'score': score,
                'total': total,
                'percentage': round(percentage, 1),
                'topic': quiz['topic']
            }
            
            # Clean up
            del self.active_quizzes[quiz_id]
        else:
            # Send next question
            next_q = questions[question_index + 1]
            response['next_question'] = self._format_question(
                next_q, 
                question_index + 1, 
                len(questions)
            )
        
        return response
    
    def generate_recommendations(self, quiz_data, incorrect_answers):
        """
        Generate personalized study recommendations based on quiz performance
        
        Args:
            quiz_data: Quiz information (topic, questions, etc.)
            incorrect_answers: List of questions the user got wrong
        
        Returns:
            dict: Recommendations with weak topics and study suggestions
        """
        
        if not incorrect_answers or len(incorrect_answers) == 0:
            # Perfect score - general encouragement
            return {
                'weak_topics': [],
                'recommendations': [{
                    'priority': 'high',
                    'topic': 'Advanced Topics',
                    'description': 'Excellent work! Consider exploring advanced Java topics.',
                    'study_points': [
                        'Explore Java Streams and Functional Programming',
                        'Learn about Design Patterns',
                        'Study Java Performance Optimization',
                        'Dive into Concurrent Programming'
                    ]
                }],
                'overall_message': '🌟 Perfect score! You have mastered this topic!'
            }
        
        # Analyze weak areas
        topic_errors = {}
        for answer in incorrect_answers:
            question_text = answer.get('question', '')
            topic = self._identify_topic_from_question(question_text, quiz_data.get('topic', 'Unknown'))
            
            if topic not in topic_errors:
                topic_errors[topic] = []
            topic_errors[topic].append(question_text)
        
        # Sort topics by number of errors (most errors first)
        weak_topics = sorted(topic_errors.keys(), key=lambda t: len(topic_errors[t]), reverse=True)
        
        # Generate AI recommendations for each weak topic
        recommendations = []
        
        for topic in weak_topics[:3]:  # Focus on top 3 weak areas
            questions_missed = topic_errors[topic]
            recommendation = self._generate_topic_recommendation(topic, questions_missed)
            recommendations.append(recommendation)
        
        # Generate overall study message
        score_percentage = ((len(quiz_data['questions']) - len(incorrect_answers)) / 
                        len(quiz_data['questions']) * 100)
        
        if score_percentage >= 70:
            overall_msg = f"📚 Good effort! You scored {score_percentage:.0f}%. Focus on the areas below to improve further."
        elif score_percentage >= 50:
            overall_msg = f"💪 Keep practicing! You scored {score_percentage:.0f}%. Review these key concepts."
        else:
            overall_msg = f"🎯 Let's strengthen your foundation! You scored {score_percentage:.0f}%. These topics need attention."
        
        return {
            'weak_topics': weak_topics,
            'recommendations': recommendations,
            'overall_message': overall_msg
        }

    def _identify_topic_from_question(self, question_text, quiz_topic):
        """Identify the specific Java topic from question text"""
        question_lower = question_text.lower()
        
        # Topic keyword mapping
        topic_map = {
            'Data Types & Variables': ['int', 'string', 'float', 'double', 'variable', 'data type', 'primitive'],
            'Control Flow': ['loop', 'if', 'else', 'switch', 'for', 'while', 'do-while', 'break', 'continue'],
            'Object-Oriented Programming': ['class', 'object', 'inheritance', 'polymorphism', 'encapsulation', 'abstraction', 'interface', 'extends', 'implements'],
            'Methods & Functions': ['method', 'function', 'return', 'parameter', 'argument', 'void', 'static'],
            'Collections': ['arraylist', 'linkedlist', 'hashmap', 'hashset', 'collection', 'list', 'set', 'map'],
            'Exception Handling': ['exception', 'try', 'catch', 'finally', 'throw', 'throws', 'error'],
            'Multithreading': ['thread', 'runnable', 'synchronized', 'concurrent', 'parallel'],
            'File I/O': ['file', 'read', 'write', 'stream', 'input', 'output', 'buffered'],
            'String Manipulation': ['string', 'substring', 'concat', 'split', 'replace', 'trim'],
            'Arrays': ['array', 'index', 'length', 'element']
        }
        
        # Check for specific topics
        for topic, keywords in topic_map.items():
            if any(keyword in question_lower for keyword in keywords):
                return topic
        
        # Default to quiz topic if no specific match
        return quiz_topic

    def _generate_topic_recommendation(self, topic, questions_missed):
        """Generate AI-powered study recommendations for a specific topic"""
        
        # Build prompt for AI
        system_prompt = """You are a Java programming tutor providing study recommendations. 
    Generate concise, actionable study suggestions for students who struggled with specific questions.
    Focus on practical learning steps and key concepts to review."""
        
        questions_text = "\n".join([f"- {q}" for q in questions_missed[:2]])  # First 2 questions
        
        user_prompt = f"""A student struggled with these questions about {topic}:

    {questions_text}

    Provide 4 specific study recommendations as a JSON array of strings. Each recommendation should be:
    - Actionable and specific
    - Focus on understanding the concept
    - Include practical examples where possible

    Format: {{"study_points": ["point 1", "point 2", "point 3", "point 4"]}}"""
        
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]
        
        try:
            # Generate recommendations using AI
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt"
            ).to(self.device)
            
            attention_mask = torch.ones_like(inputs)
            
            outputs = self.model.generate(
                inputs,
                attention_mask=attention_mask,
                max_new_tokens=400,
                do_sample=True,
                top_k=40,
                top_p=0.9,
                temperature=0.7,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
            
            response = self.tokenizer.decode(
                outputs[0][len(inputs[0]):],
                skip_special_tokens=True
            ).strip()
            
            # Try to parse JSON response
            import json
            import re
            
            json_match = re.search(r'\{[\s\S]*"study_points"[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group(0))
                study_points = data.get('study_points', [])
            else:
                # Fallback if JSON parsing fails
                study_points = self._get_fallback_recommendations(topic)
            
        except Exception as e:
            print(f"Error generating AI recommendations: {e}")
            study_points = self._get_fallback_recommendations(topic)
        
        # Determine priority based on number of questions missed
        priority = 'high' if len(questions_missed) >= 2 else 'medium'
        
        return {
            'priority': priority,
            'topic': topic,
            'description': f'Review fundamental concepts of {topic}',
            'study_points': study_points[:4],  # Limit to 4 points
            'questions_missed': len(questions_missed)
        }

    def _get_fallback_recommendations(self, topic):
        """Fallback recommendations if AI generation fails"""
        fallback_map = {
            'Data Types & Variables': [
                'Review primitive data types: byte, short, int, long, float, double, boolean, char',
                'Practice variable declaration and initialization',
                'Understand type casting and conversion',
                'Study the difference between primitive and reference types'
            ],
            'Control Flow': [
                'Master if-else statements and nested conditions',
                'Practice all loop types: for, while, do-while',
                'Understand break and continue statements',
                'Learn switch-case statement usage'
            ],
            'Object-Oriented Programming': [
                'Review the four pillars: Encapsulation, Inheritance, Polymorphism, Abstraction',
                'Practice creating classes with constructors',
                'Understand method overloading vs overriding',
                'Study interfaces and abstract classes'
            ],
            'Collections': [
                'Understand List, Set, and Map interfaces',
                'Compare ArrayList vs LinkedList performance',
                'Learn HashMap and HashSet usage',
                'Practice using Collection methods and iterators'
            ],
            'Exception Handling': [
                'Master try-catch-finally blocks',
                'Understand checked vs unchecked exceptions',
                'Learn to create custom exceptions',
                'Practice proper exception handling patterns'
            ],
            'Multithreading': [
                'Understand Thread class and Runnable interface',
                'Learn thread lifecycle and states',
                'Study synchronization and thread safety',
                'Practice using ExecutorService'
            ],
            'String Manipulation': [
                'Master String methods: substring, indexOf, replace, split',
                'Understand String immutability',
                'Learn StringBuilder and StringBuffer',
                'Practice String comparison and equality'
            ],
            'Arrays': [
                'Review array declaration and initialization',
                'Practice array traversal and manipulation',
                'Understand multi-dimensional arrays',
                'Learn Arrays utility class methods'
            ]
        }
        
        return fallback_map.get(topic, [
            f'Review basic concepts of {topic}',
            f'Practice coding exercises related to {topic}',
            f'Read documentation about {topic}',
            f'Build small projects using {topic}'
        ])
        