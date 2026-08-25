import tkinter as tk
from tkinter import messagebox
from queue import Empty, Queue
import threading

from db_lib import (
    add_card, get_cards_by_tags, add_deck, get_decks, add_card_to_deck,
    get_deck_cards, get_user_card_states, DEFAULT_USER_ID, get_all_tags,
    utc_now_iso, record_card_review, update_card_llm_grading_info
)
from sr_models import Card, Deck, ReviewItem, UserCardState
from llm_grading import grade_answer

def build_review_items(cards, states_by_card_id, user_id, now):
    review_items = []

    for card in cards:
        state = states_by_card_id.get(card.id)

        if state is None:
            state = UserCardState(
                user_id=user_id,
                card_id=card.id,
                next_review_time=now
            )

        review_items.append(ReviewItem(card=card, state=state))

    return review_items

def launch_deprecate_card():
    messagebox.showinfo(
        "Not Implemented",
        "Card deprecation will be added next."
    )

def launch_replace_card():
    messagebox.showinfo(
        "Not Implemented",
        "Card replacement will be added later."
    )

def launch_manage_cards():
    manage_window = tk.Toplevel(root)
    manage_window.title("Manage Cards")
    manage_window.geometry("400x300")

    button_frame = tk.Frame(manage_window)
    button_frame.pack(fill="both", expand=True, padx=40, pady=30)

    tk.Button(
        button_frame,
        text="Add Cards",
        command=add_card_launch
    ).pack(fill="x", pady=5)

    tk.Button(
        button_frame,
        text="Deprecate Cards",
        command=launch_deprecate_card
    ).pack(fill="x", pady=5)

    tk.Button(
        button_frame,
        text="Replace Cards",
        command=launch_replace_card
    ).pack(fill="x", pady=5)

    tk.Button(
        button_frame,
        text="Update LLM Grading Info",
        command=launch_update_llm_grading_info
    ).pack(fill="x", pady=5)

def launch_update_llm_grading_info():
    update_window = tk.Toplevel(root)
    update_window.title("Update LLM Grading Info")
    update_window.geometry("1500x700")

    content_frame = tk.Frame(update_window)
    content_frame.pack(fill="both", expand=True, padx=10, pady=10)
    content_frame.grid_rowconfigure(0, weight=1)
    content_frame.grid_columnconfigure(0, weight=1)
    content_frame.grid_columnconfigure(1, weight=4)
    content_frame.grid_columnconfigure(2, weight=2)

    selection_frame = tk.LabelFrame(
        content_frame,
        text="Select Card",
        padx=10,
        pady=10
    )
    selection_frame.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=(0, 5)
    )

    card_list = tk.Listbox(selection_frame, exportselection=False)
    card_list.pack(fill="both", expand=True)

    details_frame = tk.LabelFrame(
        content_frame,
        text="Current Card",
        padx=10,
        pady=10
    )
    details_frame.grid(
        row=0,
        column=1,
        sticky="nsew",
        padx=5
    )

    qna_frame = tk.Frame(details_frame)
    qna_frame.pack(fill="both", expand=True)

    question_frame = tk.LabelFrame(qna_frame, text="Question")
    question_frame.pack(
        side="left",
        fill="both",
        expand=True,
        padx=(0, 5)
    )
    question_frame.grid_rowconfigure(0, weight=1)
    question_frame.grid_columnconfigure(0, weight=1)

    question_text = tk.Text(
        question_frame,
        width=40,
        height=25,
        wrap="word",
        state="disabled"
    )
    question_text.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=5,
        pady=5
    )

    right_details = tk.Frame(qna_frame)
    right_details.pack(
        side="left",
        fill="both",
        expand=True,
        padx=(5, 0)
    )
    right_details.grid_rowconfigure(0, weight=2)
    right_details.grid_rowconfigure(1, weight=1)
    right_details.grid_rowconfigure(2, weight=1)
    right_details.grid_columnconfigure(0, weight=1)

    answer_frame = tk.LabelFrame(right_details, text="Answer")
    answer_frame.grid(
        row=0,
        column=0,
        sticky="nsew",
        pady=(0, 5)
    )
    answer_frame.grid_rowconfigure(0, weight=1)
    answer_frame.grid_columnconfigure(0, weight=1)

    answer_text = tk.Text(
        answer_frame,
        width=40,
        height=12,
        wrap="word",
        state="disabled"
    )
    answer_text.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=5,
        pady=5
    )

    criteria_frame = tk.LabelFrame(
        right_details,
        text="Grading Criteria"
    )
    criteria_frame.grid(
        row=1,
        column=0,
        sticky="nsew",
        pady=5
    )
    criteria_frame.grid_rowconfigure(0, weight=1)
    criteria_frame.grid_columnconfigure(0, weight=1)

    criteria_text = tk.Text(
        criteria_frame,
        width=40,
        height=6,
        wrap="word",
        state="disabled"
    )
    criteria_text.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=5,
        pady=5
    )

    current_llm_frame = tk.LabelFrame(
        right_details,
        text="LLM Grading Info"
    )
    current_llm_frame.grid(
        row=2,
        column=0,
        sticky="nsew",
        pady=(5, 0)
    )
    current_llm_frame.grid_rowconfigure(0, weight=1)
    current_llm_frame.grid_columnconfigure(0, weight=1)

    current_llm_text = tk.Text(
        current_llm_frame,
        width=40,
        height=6,
        wrap="word",
        state="disabled"
    )
    current_llm_text.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=5,
        pady=5
    )

    bottom_frame = tk.Frame(details_frame)
    bottom_frame.pack(fill="x", pady=(10, 0))

    tk.Label(
        bottom_frame,
        text="Tags, comma sep"
    ).pack(side="left")

    tags_var = tk.StringVar()
    tags_entry = tk.Entry(
        bottom_frame,
        textvariable=tags_var,
        state="readonly"
    )
    tags_entry.pack(
        side="left",
        fill="x",
        expand=True,
        padx=(5, 25)
    )

    grading_type = tk.StringVar()

    grading_frame = tk.Frame(bottom_frame)
    grading_frame.pack(side="left")

    tk.Label(
        grading_frame,
        text="Grading:  "
    ).pack(side="left")

    tk.Radiobutton(
        grading_frame,
        text="Scaled",
        variable=grading_type,
        value="scaled",
        state="disabled"
    ).pack(side="left", padx=5)

    tk.Radiobutton(
        grading_frame,
        text="Correct / Incorrect",
        variable=grading_type,
        value="binary",
        state="disabled"
    ).pack(side="left")

    new_llm_frame = tk.LabelFrame(
        content_frame,
        text="New LLM Instructions",
        padx=10,
        pady=10
    )
    new_llm_frame.grid(
        row=0,
        column=2,
        sticky="nsew",
        padx=(5, 0)
    )
    new_llm_frame.grid_rowconfigure(0, weight=1)
    new_llm_frame.grid_columnconfigure(0, weight=1)

    new_llm_input = tk.Text(
        new_llm_frame,
        width=35,
        wrap="word"
    )
    new_llm_input.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=5,
        pady=(5, 10)
    )

    current_cards = []
    selected_card = None

    def set_read_only_text(widget, value):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value or "")
        widget.config(state="disabled")

    def card_label(card):
        question = " ".join(card.question.split())
        return f"{card.id}: {question}"

    def display_card(card):
        nonlocal selected_card
        selected_card = card

        set_read_only_text(question_text, card.question)
        set_read_only_text(answer_text, card.answer)
        set_read_only_text(
            criteria_text,
            card.grading_criteria
        )
        set_read_only_text(
            current_llm_text,
            card.llm_grading_info
        )

        tags_var.set(", ".join(card.tags))
        grading_type.set(card.grading_type)

        new_llm_input.delete("1.0", "end")
        new_llm_input.insert(
            "1.0",
            card.llm_grading_info or ""
        )

    def select_card(event=None):
        selection = card_list.curselection()

        if selection:
            display_card(current_cards[selection[0]])

    def update_llm_info():
        if selected_card is None:
            messagebox.showerror(
                "No card selected",
                "Select a card to update.",
                parent=update_window
            )
            return

        new_info = (
            new_llm_input.get("1.0", "end-1c").strip()
            or None
        )

        try:
            update_card_llm_grading_info(
                selected_card.id,
                new_info
            )
        except Exception as error:
            messagebox.showerror(
                "Update Failed",
                str(error),
                parent=update_window
            )
            return

        selected_card.llm_grading_info = new_info
        set_read_only_text(current_llm_text, new_info)

        messagebox.showinfo(
            "Card Updated",
            "LLM grading information updated successfully.",
            parent=update_window
        )

    update_button = tk.Button(
        new_llm_frame,
        text="Update",
        command=update_llm_info
    )
    update_button.grid(
        row=1,
        column=0,
        pady=(0, 5)
    )

    card_list.bind("<<ListboxSelect>>", select_card)

    try:
        current_cards = get_cards_by_tags(["ALL"])

        for card in current_cards:
            card_list.insert("end", card_label(card))

        if current_cards:
            card_list.selection_set(0)
            display_card(current_cards[0])
    except Exception as error:
        messagebox.showerror(
            "Load Failed",
            str(error),
            parent=update_window
        )

def insert_question(
    question,
    answer,
    tags,
    grading_type,
    grading_criteria=None,
    llm_grading_info=None
):
    try:
        card = Card(
            question=question,
            answer=answer,
            tags=tags,
            grading_type=grading_type if grading_type in ("scaled", "binary") else None,
            grading_criteria=grading_criteria,
            llm_grading_info=llm_grading_info
        )
        add_card(card)

    except (TypeError, ValueError) as error:
        messagebox.showerror("Invalid card", str(error))
        return False
    except Exception as error:
        messagebox.showerror("Add failed", str(error))
        return False

    print(f"Card added with ID {card.id}.")
    return True

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

def ai_card_review(to_review):
    if not to_review:
        messagebox.showinfo("No questions available", "No questions came up for your selected tags.")
        return

    review_window = tk.Toplevel(root)
    review_window.title("AI Review")
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
    saved_user_answer = tk.StringVar(value="")
    grade_result = {}
    result_queue = Queue()

    def current_item():
        return to_review[curr_index.get()]

    def set_readonly_text(widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def show_question():
        set_readonly_text(q_input, current_item().card.question)
        student_answer_input.delete("1.0", "end")
        saved_user_answer.set("")
        grade_result.clear()
        grader_frame.pack_forget()
        grader_controls.pack_forget()
        student_frame.pack(fill="both", expand=True)
        student_controls.pack()
        submit_answer_btn.config(text="Submit Answer", state="normal")
        student_answer_input.focus_set()

    def finish_grading(result):
        card = current_item().card
        grade_result.update(result)

        comparison = f"Your Answer:\n{saved_user_answer.get()}\n\nSuggested Answer:\n{card.answer}"
        set_readonly_text(comparison_input, comparison)
        set_readonly_text(criteria_input, card.grading_criteria or "No grading criteria provided.")
        set_readonly_text(llm_input, card.llm_grading_info or "No additional LLM grading information provided.")

        score_text = "Manual grading required" if result["requires_manual_grading"] else f"Score: {result['score']}"
        set_readonly_text(feedback_input, f"{score_text}\n\n{result['feedback']}")

        student_frame.pack_forget()
        student_controls.pack_forget()
        grader_frame.pack(fill="both", expand=True)
        grader_controls.pack()
        save_grade_btn.config(state="normal")

    def poll_for_grade():
        try:
            status, result = result_queue.get_nowait()
        except Empty:
            review_window.after(100, poll_for_grade)
            return

        if status == "error":
            submit_answer_btn.config(text="Submit Answer", state="normal")
            messagebox.showerror("AI grading error", str(result))
            return

        finish_grading(result)

    def submit_answer():
        review_item = current_item()
        user_answer = student_answer_input.get("1.0", "end-1c").strip()
        saved_user_answer.set(user_answer)
        submit_answer_btn.config(text="Grading...", state="disabled")

        def run_grader():
            try:
                result_queue.put(("success", grade_answer(review_item.card, user_answer)))
            except Exception as error:
                result_queue.put(("error", error))

        threading.Thread(target=run_grader, daemon=True).start()
        review_window.after(100, poll_for_grade)

    def submit_grade_and_next():
        save_grade_btn.config(state="disabled")

        try:
            record_card_review(
                review_item=current_item(),
                score=grade_result["score"],
                grading_mode="ai",
                user_answer=saved_user_answer.get(),
                ai_feedback=grade_result["feedback"],
                llm_call_id=grade_result["llm_call_id"]
            )
        except Exception as error:
            save_grade_btn.config(state="normal")
            messagebox.showerror("Review not saved", str(error))
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

    save_grade_btn = tk.Button(
        grader_controls,
        text="Save Result / Next",
        command=submit_grade_and_next,
        state="disabled"
    )
    save_grade_btn.pack(side="left", padx=10)

    show_question()

def launch_review_menu():
    config_window = tk.Toplevel(root)
    config_window.title("Review Config")
    config_window.geometry("400x500")

    # grading section
    grading_frame = tk.LabelFrame(config_window, text="Grading", padx=10, pady=10)
    grading_frame.pack(fill="x", padx=10, pady=10)

    grading_mode = tk.StringVar(value="Manual")

    tk.Radiobutton(
        grading_frame,
        text="Manual",
        variable=grading_mode,
        value="Manual"
    ).pack(anchor="w")

    tk.Radiobutton(
        grading_frame,
        text="AI",
        variable=grading_mode,
        value="AI"
    ).pack(anchor="w")

    # number of cards section
    count_frame = tk.LabelFrame(config_window, text="Number of cards", padx=10, pady=10)
    count_frame.pack(fill="x", padx=10, pady=10)

    card_count_input = tk.Entry(count_frame, width=20)
    card_count_input.pack(anchor="w")

    # review source section
    source_frame = tk.LabelFrame(config_window, text="Review Source", padx=10, pady=10)
    source_frame.pack(fill="x", padx=10, pady=10)

    review_source = tk.StringVar(value="Tags")

    available_tags = ["ALL"] + get_all_tags()
    selected_tag = tk.StringVar(value="ALL")

    current_decks = get_decks(user_id=DEFAULT_USER_ID)
    deck_names = [deck.name for deck in current_decks]
    selected_deck = tk.StringVar(value=deck_names[0] if deck_names else "")

    tag_radio = tk.Radiobutton(
        source_frame,
        text="Tags",
        variable=review_source,
        value="Tags"
    )
    tag_radio.grid(row=0, column=0, sticky="w")

    tag_menu = tk.OptionMenu(source_frame, selected_tag, *available_tags)
    tag_menu.grid(row=0, column=1, sticky="w", padx=(10, 0))

    deck_radio = tk.Radiobutton(
        source_frame,
        text="Deck",
        variable=review_source,
        value="Deck"
    )
    deck_radio.grid(row=1, column=0, sticky="w", pady=(10, 0))

    if deck_names:
        deck_menu = tk.OptionMenu(source_frame, selected_deck, *deck_names)
    else:
        deck_menu = tk.OptionMenu(source_frame, selected_deck, "")

    deck_menu.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(10, 0))

    def update_source_controls():
        if review_source.get() == "Tags":
            tag_menu.config(state="normal")
            deck_menu.config(state="disabled")
        else:
            tag_menu.config(state="disabled")
            deck_menu.config(state="normal")

    tag_radio.config(command=update_source_controls)
    deck_radio.config(command=update_source_controls)
    update_source_controls()

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
        review_callback = manual_card_review if mode == "Manual" else ai_card_review

        if review_source.get() == "Deck":
            if not current_decks:
                messagebox.showerror("No decks", "You do not have any decks to review.")
                return

            deck = next(
                deck for deck in current_decks
                if deck.name == selected_deck.get()
            )
            cards = get_deck_cards(deck)
        else:
            selected = selected_tag.get()
            review_tags = ["ALL"] if selected == "ALL" else [selected]
            cards = get_cards_by_tags(review_tags)

        now = utc_now_iso()
        states_by_card_id = get_user_card_states(DEFAULT_USER_ID)

        review_items = build_review_items(
            cards,
            states_by_card_id,
            DEFAULT_USER_ID,
            now
        )

        due_items = [
            review_item for review_item in review_items
            if review_item.is_due(now)
        ]
        early_items = [
            review_item for review_item in review_items
            if not review_item.is_due(now)
        ]
        early_items.sort(
            key=lambda review_item: review_item.state.next_review_time
        )

        if not due_items and not early_items:
            messagebox.showinfo(
                "No questions available",
                "No questions came up for your selected review source."
            )
            return

        if len(due_items) >= card_count:
            config_window.destroy()
            review_callback(due_items[:card_count])
            return

        if not early_items:
            config_window.destroy()
            review_callback(due_items)
            return

        launch_early_review_popup(
            parent=config_window,
            due_items=due_items,
            early_items=early_items,
            card_count=card_count,
            review_callback=review_callback
        )

    start_btn = tk.Button(config_window, text="Start Review", command=start_review)
    start_btn.pack(pady=10)

def launch_early_review_popup(parent, due_items, early_items, card_count, review_callback):
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
            to_review = (due_items + early_items)[:card_count]
        else:
            to_review = due_items

        popup.destroy()
        parent.destroy()
        review_callback(to_review)

    tk.Button(popup, text="Review", command=start_review_from_popup).pack(pady=20)

def manual_card_review(to_review):
    if not to_review:
        messagebox.showinfo("No questions available", "No questions came up for your selected tags.")
        return

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

    def show_question():
        review_item = to_review[curr_index.get()]
        selected_grade.set(0)
        answer_shown.set(False)
        saved_user_answer.set("")

        q_input.config(state="normal")
        q_input.delete("1.0", "end")
        q_input.insert("1.0", review_item.card.question)
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

        review_item = to_review[curr_index.get()]
        user_answer = a_input.get("1.0", "end-1c").strip()
        saved_user_answer.set(user_answer)

        a_label.config(text="Answer Comparison")

        a_input.config(state="normal")
        a_input.delete("1.0", "end")
        a_input.insert("1.0", f"Your Answer:\n{user_answer}\n\n")
        a_input.insert("end", f"Suggested Answer:\n{review_item.card.answer}\n\n")
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

        review_item = to_review[curr_index.get()]
        submit_grade_btn.config(state="disabled")

        try:
            record_card_review(
                review_item=review_item,
                score=grade,
                grading_mode="manual",
                user_answer=saved_user_answer.get()
            )
        except (TypeError, ValueError) as error:
            submit_grade_btn.config(state="normal")
            messagebox.showerror("Invalid review", str(error))
            return
        except Exception as error:
            submit_grade_btn.config(state="normal")
            messagebox.showerror("Review not saved", str(error))
            return

        next_index = curr_index.get() + 1

        if next_index >= len(to_review):
            messagebox.showinfo("Done", "All cards reviewed!")
            review_window.destroy()
            return

        curr_index.set(next_index)
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

def launch_manage_decks():
    manage_window = tk.Toplevel(root)
    manage_window.title("Manage Decks")
    manage_window.geometry("500x400")

    create_frame = tk.LabelFrame(manage_window, text="Create Deck", padx=10, pady=10)
    create_frame.pack(fill="x", padx=10, pady=10)

    tk.Label(create_frame, text="Deck name").pack(side="left")

    deck_name_input = tk.Entry(create_frame, width=35)
    deck_name_input.pack(side="left", padx=10, fill="x", expand=True)

    decks_frame = tk.LabelFrame(manage_window, text="Your Decks", padx=10, pady=10)
    decks_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    deck_list = tk.Listbox(decks_frame)
    deck_list.pack(fill="both", expand=True)

    current_decks = []

    def refresh_decks(selected_deck_id=None):
        nonlocal current_decks

        current_decks = get_decks(user_id=DEFAULT_USER_ID)
        deck_list.delete(0, "end")

        for index, deck in enumerate(current_decks):
            deck_list.insert("end", deck.name)

            if deck.id == selected_deck_id:
                deck_list.selection_set(index)
                deck_list.see(index)

    def create_deck():
        try:
            deck = add_deck(Deck(
                name=deck_name_input.get(),
                owner_user_id=DEFAULT_USER_ID
            ))
        except (TypeError, ValueError) as error:
            messagebox.showerror("Invalid deck", str(error), parent=manage_window)
            return
        except Exception as error:
            messagebox.showerror("Create failed", str(error), parent=manage_window)
            return

        deck_name_input.delete(0, "end")
        refresh_decks(selected_deck_id=deck.id)

    def edit_selected_deck():
        selection = deck_list.curselection()

        if not selection:
            messagebox.showerror(
                "No deck selected",
                "Select a deck to edit.",
                parent=manage_window
            )
            return

        launch_edit_deck(current_decks[selection[0]])

    create_button = tk.Button(create_frame, text="Create", command=create_deck)
    create_button.pack(side="left")

    edit_button = tk.Button(
        decks_frame,
        text="Edit Selected Deck",
        command=edit_selected_deck
    )
    edit_button.pack(pady=(10, 0))

    deck_name_input.bind("<Return>", lambda event: create_deck())
    deck_list.bind("<Double-Button-1>", lambda event: edit_selected_deck())
    deck_name_input.focus_set()

    try:
        refresh_decks()
    except Exception as error:
        messagebox.showerror("Load failed", str(error), parent=manage_window)

def launch_edit_deck(deck):
    edit_window = tk.Toplevel(root)
    edit_window.title(f"Edit Deck: {deck.name}")
    edit_window.geometry("900x550")

    lists_frame = tk.Frame(edit_window)
    lists_frame.pack(fill="both", expand=True, padx=15, pady=15)
    lists_frame.grid_rowconfigure(0, weight=1)
    lists_frame.grid_columnconfigure(0, weight=1)
    lists_frame.grid_columnconfigure(2, weight=1)

    used_frame = tk.LabelFrame(lists_frame, text="Cards Used", padx=10, pady=10)
    used_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

    separator = tk.Frame(lists_frame, width=2, bg="gray")
    separator.grid(row=0, column=1, sticky="ns")

    available_frame = tk.LabelFrame(lists_frame, text="Cards to Add", padx=10, pady=10)
    available_frame.grid(row=0, column=2, sticky="nsew", padx=(15, 0))

    used_card_list = tk.Listbox(used_frame)
    used_card_list.pack(fill="both", expand=True)

    available_card_list = tk.Listbox(available_frame)
    available_card_list.pack(fill="both", expand=True)

    cards_to_add = []

    def card_label(card):
        return f"{card.id}: {' '.join(card.question.split())}"

    def refresh_cards():
        nonlocal cards_to_add

        all_cards = get_cards_by_tags(["ALL"])
        used_cards = get_deck_cards(deck)
        used_card_ids = {card.id for card in used_cards}
        cards_to_add = [
            card for card in all_cards
            if card.id not in used_card_ids
        ]

        used_card_list.delete(0, "end")
        available_card_list.delete(0, "end")

        for card in used_cards:
            used_card_list.insert("end", card_label(card))

        for card in cards_to_add:
            available_card_list.insert("end", card_label(card))

    def add_selected_card():
        selection = available_card_list.curselection()

        if not selection:
            messagebox.showerror(
                "No card selected",
                "Select a card to add.",
                parent=edit_window
            )
            return

        card = cards_to_add[selection[0]]

        try:
            add_card_to_deck(deck, card)
            refresh_cards()
        except Exception as error:
            messagebox.showerror("Add failed", str(error), parent=edit_window)

    add_button = tk.Button(
        available_frame,
        text="Add Selected Card",
        command=add_selected_card
    )
    add_button.pack(pady=(10, 0))

    try:
        refresh_cards()
    except Exception as error:
        messagebox.showerror("Load failed", str(error), parent=edit_window)

root = tk.Tk()
root.title("Spaced Repetion Practice")
root.geometry("300x100")

frame = tk.Frame(root)
frame.pack(expand=True)

manage_cards_btn = tk.Button(frame,text="Manage Cards",command=launch_manage_cards)
manage_cards_btn.pack(side="left", padx=5)

review_card_btn = tk.Button(frame, text="Review Questions", command=launch_review_menu)
review_card_btn.pack(side = "left", padx=5)

manage_decks_btn = tk.Button(frame, text="Manage Decks", command=launch_manage_decks)
manage_decks_btn.pack(side="left", padx=5)

root.mainloop()