import tkinter as tk
from tkinter import messagebox
from db_lib import add_card, get_cards, get_all_tags, utc_now_iso, record_card_review
from ai_grading import validate_grade_result

def insert_question(question, answer, tags, grading_type, grading_criteria=None, llm_grading_info=None):
    question = question.strip()
    answer = answer.strip()
    grading_criteria = grading_criteria.strip() if grading_criteria else None
    llm_grading_info = llm_grading_info.strip() if llm_grading_info else None

    if not question:
        messagebox.showerror("Missing question", "Question cannot be blank.")
        return False
    if not answer:
        messagebox.showerror("Missing answer", "Answer cannot be blank.")
        return False
    if grading_type not in ("scaled", "binary"):
        messagebox.showerror("Missing grading type", "Choose a grading type.")
        return False

    added = add_card(
        question,
        answer,
        tags,
        grading_type=grading_type,
        grading_criteria=grading_criteria,
        llm_grading_info=llm_grading_info
    )

    if added.get("success"):
        print("Card added.")
        return True

    print("Error:", added.get("error"))
    messagebox.showerror("Add failed", added.get("error", "Unknown error"))
    return False

def add_card_launch():
    add_window = tk.Toplevel(root)
    add_window.title("Add Question")
    add_window.geometry("1100x650")

    qna_frame = tk.Frame(add_window)
    qna_frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)

    q_frame = tk.LabelFrame(qna_frame, text="Question")
    q_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
    q_frame.grid_rowconfigure(0, weight=1)
    q_frame.grid_columnconfigure(0, weight=1)

    q_input = tk.Text(q_frame, width=50, height=25, wrap="word")
    q_input.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    right_frame = tk.Frame(qna_frame)
    right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
    right_frame.grid_rowconfigure(0, weight=2)
    right_frame.grid_rowconfigure(1, weight=1)
    right_frame.grid_rowconfigure(2, weight=1)
    right_frame.grid_columnconfigure(0, weight=1)

    answer_frame = tk.LabelFrame(right_frame, text="Answer")
    answer_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
    answer_frame.grid_rowconfigure(0, weight=1)
    answer_frame.grid_columnconfigure(0, weight=1)

    a_input = tk.Text(answer_frame, width=50, height=12, wrap="word")
    a_input.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    criteria_frame = tk.LabelFrame(right_frame, text="Grading Criteria")
    criteria_frame.grid(row=1, column=0, sticky="nsew", pady=5)
    criteria_frame.grid_rowconfigure(0, weight=1)
    criteria_frame.grid_columnconfigure(0, weight=1)

    criteria_input = tk.Text(criteria_frame, width=50, height=6, wrap="word")
    criteria_input.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    llm_frame = tk.LabelFrame(right_frame, text="LLM Grading Info")
    llm_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
    llm_frame.grid_rowconfigure(0, weight=1)
    llm_frame.grid_columnconfigure(0, weight=1)

    llm_info_input = tk.Text(llm_frame, width=50, height=6, wrap="word")
    llm_info_input.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    bottom_frame = tk.Frame(add_window)
    bottom_frame.pack(side="bottom", pady=10)

    input_row = tk.Frame(bottom_frame)
    input_row.pack(side="top", pady=(0, 10))

    tag_label = tk.Label(input_row, text="Tags, comma sep")
    tag_label.pack(side="left")

    tags_input = tk.Entry(input_row, width=55)
    tags_input.pack(side="left", padx=(5, 45))

    grading_type = tk.StringVar(value="unselected")

    grading_frame = tk.Frame(input_row)
    grading_frame.pack(side="left")

    tk.Label(grading_frame, text="Grading:  ").pack(side="left", padx=(0, 0))

    scaled_radio = tk.Radiobutton(
        grading_frame,
        text="Scaled",
        variable=grading_type,
        value="scaled"
    )
    scaled_radio.pack(side="left", padx=(5, 5))

    binary_radio = tk.Radiobutton(
        grading_frame,
        text="Correct / Incorrect",
        variable=grading_type,
        value="binary"
    )
    binary_radio.pack(side="left")

    def add_handler():
        q_text = q_input.get("1.0", "end-1c")
        a_text = a_input.get("1.0", "end-1c")
        criteria_text = criteria_input.get("1.0", "end-1c")
        llm_info_text = llm_info_input.get("1.0", "end-1c")
        tag_text = [t.strip() for t in tags_input.get().split(",") if t.strip()]

        if insert_question(q_text, a_text, tag_text, grading_type.get(), criteria_text, llm_info_text):
            q_input.delete("1.0", "end")
            a_input.delete("1.0", "end")
            criteria_input.delete("1.0", "end")
            llm_info_input.delete("1.0", "end")
            tags_input.delete(0, "end")
            grading_type.set("unselected")

    add_button = tk.Button(bottom_frame, text="Add Question", command=add_handler)
    add_button.pack(side="top")

def dummy_ai_card_review(to_review):
    if not to_review:
        messagebox.showinfo("No questions available", "No questions came up for your selected tags.")
        return

    review_window = tk.Toplevel(root)
    review_window.title("Dummy AI Review")
    review_window.geometry("1200x750")

    qna_frame = tk.Frame(review_window)
    qna_frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)

    q_frame = tk.LabelFrame(qna_frame, text="Question")
    q_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

    q_input = tk.Text(q_frame, width=60, height=30, wrap="word")
    q_input.pack(fill="both", expand=True, padx=5, pady=5)

    right_frame = tk.Frame(qna_frame)
    right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))

    student_frame = tk.LabelFrame(right_frame, text="Your Answer")
    student_answer_input = tk.Text(student_frame, width=60, height=30, wrap="word")
    student_answer_input.pack(fill="both", expand=True, padx=5, pady=5)

    grader_frame = tk.Frame(right_frame)
    grader_frame.grid_rowconfigure(0, weight=3)
    grader_frame.grid_rowconfigure(1, weight=1)
    grader_frame.grid_rowconfigure(2, weight=1)
    grader_frame.grid_rowconfigure(3, weight=2)
    grader_frame.grid_columnconfigure(0, weight=1)

    comparison_frame = tk.LabelFrame(grader_frame, text="Answer Comparison")
    comparison_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

    comparison_input = tk.Text(comparison_frame, width=60, height=14, wrap="word")
    comparison_input.pack(fill="both", expand=True, padx=5, pady=5)

    criteria_frame = tk.LabelFrame(grader_frame, text="Grading Criteria")
    criteria_frame.grid(row=1, column=0, sticky="nsew", pady=5)

    criteria_input = tk.Text(criteria_frame, width=60, height=5, wrap="word")
    criteria_input.pack(fill="both", expand=True, padx=5, pady=5)

    llm_frame = tk.LabelFrame(grader_frame, text="LLM Grading Info")
    llm_frame.grid(row=2, column=0, sticky="nsew", pady=5)

    llm_input = tk.Text(llm_frame, width=60, height=5, wrap="word")
    llm_input.pack(fill="both", expand=True, padx=5, pady=5)

    feedback_frame = tk.LabelFrame(grader_frame, text="AI Feedback")
    feedback_frame.grid(row=3, column=0, sticky="nsew", pady=(5, 0))

    feedback_input = tk.Text(feedback_frame, width=60, height=8, wrap="word")
    feedback_input.pack(fill="both", expand=True, padx=5, pady=5)

    bottom_frame = tk.Frame(review_window)
    bottom_frame.pack(side="bottom", pady=10)

    student_controls = tk.Frame(bottom_frame)
    grader_controls = tk.Frame(bottom_frame)

    curr_index = tk.IntVar(value=0)
    selected_grade = tk.IntVar(value=0)
    saved_user_answer = tk.StringVar(value="")
    grade_buttons = []

    def set_readonly_text(widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def choose_grade(grade):
        selected_grade.set(grade)
        save_grade_btn.config(state="normal")

    def configure_grade_buttons(card):
        for button in grade_buttons:
            button.destroy()

        grade_buttons.clear()
        selected_grade.set(0)
        save_grade_btn.config(state="disabled")

        if card["grading_type"] == "binary":
            grade_options = [("Incorrect", 1), ("Correct", 5)]
        else:
            grade_options = [(str(grade), grade) for grade in range(1, 6)]

        for label, grade in grade_options:
            button = tk.Radiobutton(
                grade_frame,
                text=label,
                variable=selected_grade,
                value=grade,
                command=lambda g=grade: choose_grade(g)
            )
            button.pack(side="left")
            grade_buttons.append(button)

    def show_question():
        card = to_review[curr_index.get()]

        set_readonly_text(q_input, card["question"])
        student_answer_input.delete("1.0", "end")
        saved_user_answer.set("")
        selected_grade.set(0)

        grader_frame.pack_forget()
        grader_controls.pack_forget()
        student_frame.pack(fill="both", expand=True)
        student_controls.pack()
        student_answer_input.focus_set()

    def submit_answer():
        card = to_review[curr_index.get()]
        user_answer = student_answer_input.get("1.0", "end-1c").strip()
        saved_user_answer.set(user_answer)

        comparison_text = f"Your Answer:\n{user_answer}\n\nSuggested Answer:\n{card['answer']}"

        set_readonly_text(comparison_input, comparison_text)
        set_readonly_text(criteria_input, card.get("grading_criteria") or "No grading criteria provided.")
        set_readonly_text(llm_input, card.get("llm_grading_info") or "No additional LLM grading information provided.")

        feedback_input.delete("1.0", "end")
        configure_grade_buttons(card)

        student_frame.pack_forget()
        student_controls.pack_forget()
        grader_frame.pack(fill="both", expand=True)
        grader_controls.pack()
        feedback_input.focus_set()

    def submit_grade_and_next():
        card = to_review[curr_index.get()]

        try:
            grade_result = validate_grade_result(card, {
                "score": selected_grade.get(),
                "feedback": feedback_input.get("1.0", "end-1c")
            })
        except (TypeError, ValueError) as e:
            messagebox.showerror("Invalid grade result", str(e))
            return

        result = record_card_review(
            card_id=card["id"],
            score=grade_result["score"],
            grading_mode="ai",
            user_answer=saved_user_answer.get(),
            ai_feedback=grade_result["feedback"]
        )

        if not result.get("success"):
            messagebox.showerror("Review not saved", result.get("error", "Unknown database error"))
            return

        next_index = curr_index.get() + 1
        if next_index >= len(to_review):
            messagebox.showinfo("Done", "All cards reviewed!")
            review_window.destroy()
            return

        curr_index.set(next_index)
        show_question()

    submit_answer_btn = tk.Button(student_controls, text="Submit Answer", command=submit_answer)
    submit_answer_btn.pack()

    grade_frame = tk.Frame(grader_controls)
    grade_frame.pack(side="left", padx=20)

    tk.Label(grade_frame, text="Grade:").pack(side="left", padx=(0, 5))

    save_grade_btn = tk.Button(
        grader_controls,
        text="Save Grade / Next",
        command=submit_grade_and_next,
        state="disabled"
    )
    save_grade_btn.pack(side="left", padx=10)

    show_question()

def launch_review_menu():
    config_window = tk.Toplevel(root)
    config_window.title("Review Config")
    config_window.geometry("400x400")

    # grading section
    grading_frame = tk.LabelFrame(config_window, text="Grading", padx=10, pady=10)
    grading_frame.pack(fill="x", padx=10, pady=10)

    grading_mode = tk.StringVar(value="Manual")

    manual_radio = tk.Radiobutton(
        grading_frame,
        text="Manual",
        variable=grading_mode,
        value="Manual"
    )
    manual_radio.pack(anchor="w")

    ai_radio = tk.Radiobutton(
        grading_frame,
        text="AI",
        variable=grading_mode,
        value="AI"
    )
    ai_radio.pack(anchor="w")

    # number of cards section
    count_frame = tk.LabelFrame(config_window, text="Number of cards", padx=10, pady=10)
    count_frame.pack(fill="x", padx=10, pady=10)

    card_count_input = tk.Entry(count_frame, width=20)
    card_count_input.pack(anchor="w")

    # subjects section
    subjects_frame = tk.LabelFrame(config_window, text="Tags", padx=10, pady=10)
    subjects_frame.pack(fill="x", padx=10, pady=10)

    available_tags = ["ALL"] + get_all_tags()

    selected_tag = tk.StringVar(value="ALL")

    tag_menu = tk.OptionMenu(subjects_frame, selected_tag, *available_tags)
    tag_menu.pack(anchor="w")

    def start_review():
        card_count_text = card_count_input.get().strip()

        try:
            card_count = int(card_count_text)
        except ValueError:
            messagebox.showerror("Invalid number", "Number of cards must be a positive integer.")
            return

        if card_count <= 0:
            messagebox.showerror("Invalid number", "Number of cards must be a positive integer.")
            return

        mode = grading_mode.get()
        review_callback = manual_card_review if mode == "Manual" else dummy_ai_card_review

        selected = selected_tag.get()
        review_tags = ["ALL"] if selected == "ALL" else [selected]

        cards = get_cards(review_tags)
        now = utc_now_iso()

        due_cards = [card for card in cards if card["next_review_time"] <= now]
        early_cards = [card for card in cards if card["next_review_time"] > now]
        early_cards.sort(key=lambda card: card["next_review_time"])

        if not due_cards and not early_cards:
            messagebox.showinfo("No questions available", "No questions came up for your selected tags.")
            return

        if len(due_cards) >= card_count:
            config_window.destroy()
            review_callback(due_cards[:card_count])
            return

        if not early_cards:
            config_window.destroy()
            review_callback(due_cards)
            return

        launch_early_review_popup(
            parent=config_window,
            due_cards=due_cards,
            early_cards=early_cards,
            card_count=card_count,
            review_callback=review_callback
        )

    start_btn = tk.Button(config_window, text="Start Review", command=start_review)
    start_btn.pack(pady=10)

def launch_early_review_popup(
    parent,
    due_cards,
    early_cards,
    card_count,
    review_callback
):
    popup = tk.Toplevel(parent)
    popup.title("Review Early?")
    popup.geometry("500x220")
    popup.transient(parent)
    popup.grab_set()

    choice = tk.StringVar(value="due_only")

    message = tk.Label(
        popup,
        text="Fewer cards are due for review than you selected, would you like to review additional cards early?",
        wraplength=450,
        justify="left"
    )
    message.pack(anchor="w", padx=20, pady=(20, 10))

    tk.Radiobutton(
        popup,
        text="Review only cards due for review",
        variable=choice,
        value="due_only"
    ).pack(anchor="w", padx=20, pady=(5, 2))

    tk.Radiobutton(
        popup,
        text="Review additional cards early",
        variable=choice,
        value="include_early"
    ).pack(anchor="w", padx=20, pady=2)

    def start_review_from_popup():
        if choice.get() == "include_early":
            to_review = (due_cards + early_cards)[:card_count]
        else:
            to_review = due_cards

        popup.destroy()
        parent.destroy()
        review_callback(to_review)

    tk.Button(
        popup,
        text="Review",
        command=start_review_from_popup
    ).pack(pady=20)

def manual_card_review(to_review):
    review_window = tk.Toplevel(root)
    review_window.title("Manual Review")
    review_window.geometry("1200x700")

    qna_frame = tk.Frame(review_window)
    qna_frame.pack(side="top", fill="both", expand=True)

    q_frame = tk.Frame(qna_frame)
    q_frame.pack(side="left", fill="both", expand=True)

    q_label = tk.Label(q_frame, text="Question")
    q_label.pack(pady=(0, 5))

    q_input = tk.Text(q_frame, width=70, height=30, wrap="word")
    q_input.pack(padx=5, pady=3, fill="both", expand=True)

    a_frame = tk.Frame(qna_frame)
    a_frame.pack(side="left", fill="both", expand=True)

    a_label = tk.Label(a_frame, text="Your Answer")
    a_label.pack(pady=(0, 5))

    a_input = tk.Text(a_frame, width=70, height=30, wrap="word")
    a_input.pack(padx=5, pady=3, fill="both", expand=True)

    bottom_frame = tk.Frame(review_window)
    bottom_frame.pack(side="bottom", pady=10)

    curr_index = tk.IntVar(value=0)
    answer_shown = tk.BooleanVar(value=False)
    selected_grade = tk.IntVar(value=0)
    saved_user_answer = tk.StringVar(value="")

    if not to_review:
        messagebox.showinfo("No questions available", "No questions came up for your selected tags.")
        review_window.destroy()
        return

    def show_question():
        card = to_review[curr_index.get()]
        selected_grade.set(0)
        answer_shown.set(False)
        saved_user_answer.set("")

        q_input.config(state="normal")
        q_input.delete("1.0", "end")
        q_input.insert("1.0", card["question"])
        q_input.config(state="disabled")

        a_label.config(text="Your Answer")

        a_input.config(state="normal")
        a_input.delete("1.0", "end")

        show_ans_btn.config(state="normal")
        submit_grade_btn.config(state="disabled")

        for btn in grade_buttons:
            btn.config(state="disabled")

    def reveal_answer():
        if answer_shown.get():
            return

        card = to_review[curr_index.get()]
        user_answer = a_input.get("1.0", "end-1c").strip()
        saved_user_answer.set(user_answer)

        a_label.config(text="Answer Comparison")

        a_input.config(state="normal")
        a_input.delete("1.0", "end")
        a_input.insert("1.0", f"Your Answer:\n{user_answer}\n\n")
        a_input.insert("end", f"Suggested Answer:\n{card['answer']}\n\n")
        a_input.insert("end", "Select a grade below.")

        a_input.config(state="disabled")
        answer_shown.set(True)

        show_ans_btn.config(state="disabled")

        for btn in grade_buttons:
            btn.config(state="normal")

    def choose_grade(grade):
        selected_grade.set(grade)
        submit_grade_btn.config(state="normal")

    def submit_grade_and_next():
        grade = selected_grade.get()

        if not answer_shown.get():
            messagebox.showerror("Answer not shown", "Show the answer before grading.")
            return

        if grade not in (1, 2, 3, 4, 5):
            messagebox.showerror("Missing grade", "Select a grade before continuing.")
            return

        card = to_review[curr_index.get()]

        result = record_card_review(
            card_id=card["id"],
            score=grade,
            grading_mode="manual",
            user_answer=saved_user_answer.get()
        )

        if not result.get("success"):
            messagebox.showerror(
                "Review not saved",
                result.get("error", "Unknown database error")
            )
            return

        idx = curr_index.get() + 1

        if idx >= len(to_review):
            messagebox.showinfo("Done", "All cards reviewed!")
            review_window.destroy()
            return

        curr_index.set(idx)
        show_question()

    show_ans_btn = tk.Button(bottom_frame, text="Show Answer", command=reveal_answer)
    show_ans_btn.pack(side="left", padx=10)

    grade_frame = tk.Frame(bottom_frame)
    grade_frame.pack(side="left", padx=20)

    tk.Label(grade_frame, text="Grade:").pack(side="left", padx=(0, 5))

    grade_buttons = []
    for grade in range(1, 6):
        btn = tk.Radiobutton(
            grade_frame,
            text=str(grade),
            variable=selected_grade,
            value=grade,
            command=lambda g=grade: choose_grade(g),
            state="disabled"
        )
        btn.pack(side="left")
        grade_buttons.append(btn)

    submit_grade_btn = tk.Button(
        bottom_frame,
        text="Submit Grade / Next",
        command=submit_grade_and_next,
        state="disabled"
    )
    submit_grade_btn.pack(side="left", padx=10)

    show_question()

root = tk.Tk()
root.title("Spaced Repition Practice")
root.geometry("300x100")

frame = tk.Frame(root)
frame.pack(expand=True)

add_card_btn = tk.Button(frame, text="Add Question", command=add_card_launch)
add_card_btn.pack(side="left", padx=5)

review_card_btn = tk.Button(frame, text="Review Questions", command=launch_review_menu)
review_card_btn.pack(side = "left", padx=5)

root.mainloop()