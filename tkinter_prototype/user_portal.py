import tkinter as tk
from tkinter import messagebox
from queue import Empty, Queue
import threading

from db_lib import (
    add_card, get_cards_by_tags, add_deck, get_decks, add_card_to_deck,
    get_deck_cards, deprecate_card, get_user_card_states, DEFAULT_USER_ID, get_all_tags,
    utc_now_iso, record_card_review, update_card_llm_grading_info,
)
from sr_models import Card, Deck, ReviewItem, UserCardState
from llm_calls import generate_card_drafts, grade_answer

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

def create_text_panel(parent, title, width, height, editable=True):
    frame = tk.LabelFrame(parent, text=title)
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    text = tk.Text(
        frame,
        width=width,
        height=height,
        wrap="word",
        state="normal" if editable else "disabled"
    )
    text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    return frame, text

def set_text(widget, value):
    original_state = widget.cget("state")
    widget.config(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value or "")
    widget.config(state=original_state)

class CardForm(tk.Frame):
    def __init__(self, parent, editable=True):
        super().__init__(parent)
        self.editable = editable

        qna_frame = tk.Frame(self)
        qna_frame.pack(side="top", fill="both", expand=True)

        question_frame, self.question_input = create_text_panel(
            qna_frame, "Question", 50, 25, editable
        )
        question_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        right_frame = tk.Frame(qna_frame)
        right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        right_frame.grid_rowconfigure(0, weight=2)
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        answer_frame, self.answer_input = create_text_panel(
            right_frame, "Answer", 50, 12, editable
        )
        answer_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        criteria_frame, self.criteria_input = create_text_panel(
            right_frame, "Grading Criteria", 50, 6, editable
        )
        criteria_frame.grid(row=1, column=0, sticky="nsew", pady=5)

        llm_frame, self.llm_info_input = create_text_panel(
            right_frame, "LLM Grading Info", 50, 6, editable
        )
        llm_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))

        input_row = tk.Frame(self)
        input_row.pack(side="bottom", pady=(10, 0))

        tk.Label(input_row, text="Tags, comma sep").pack(side="left")

        self.tags_input = tk.Entry(
            input_row,
            width=55,
            state="normal" if editable else "readonly"
        )
        self.tags_input.pack(side="left", padx=(5, 45))

        self.grading_type = tk.StringVar(value="unselected")
        grading_frame = tk.Frame(input_row)
        grading_frame.pack(side="left")

        tk.Label(grading_frame, text="Grading:  ").pack(side="left")
        radio_state = "normal" if editable else "disabled"

        tk.Radiobutton(
            grading_frame,
            text="Scaled",
            variable=self.grading_type,
            value="scaled",
            state=radio_state
        ).pack(side="left", padx=5)

        tk.Radiobutton(
            grading_frame,
            text="Correct / Incorrect",
            variable=self.grading_type,
            value="binary",
            state=radio_state
        ).pack(side="left")

    def get_values(self):
        return (
            self.question_input.get("1.0", "end-1c"),
            self.answer_input.get("1.0", "end-1c"),
            [tag.strip() for tag in self.tags_input.get().split(",") if tag.strip()],
            self.grading_type.get(),
            self.criteria_input.get("1.0", "end-1c"),
            self.llm_info_input.get("1.0", "end-1c")
        )

    def load_card(self, card):
        set_text(self.question_input, card.question)
        set_text(self.answer_input, card.answer)
        set_text(self.criteria_input, card.grading_criteria)
        set_text(self.llm_info_input, card.llm_grading_info)

        self.tags_input.config(state="normal")
        self.tags_input.delete(0, "end")
        self.tags_input.insert(0, ", ".join(card.tags))
        if not self.editable:
            self.tags_input.config(state="readonly")

        self.grading_type.set(card.grading_type)

    def clear(self):
        set_text(self.question_input, "")
        set_text(self.answer_input, "")
        set_text(self.criteria_input, "")
        set_text(self.llm_info_input, "")

        self.tags_input.config(state="normal")
        self.tags_input.delete(0, "end")
        if not self.editable:
            self.tags_input.config(state="readonly")

        self.grading_type.set("unselected")

class CardListPanel(tk.LabelFrame):
    def __init__(self, parent, title, filterable=False):
        super().__init__(parent, text=title, padx=10, pady=10)
        self.all_cards = []
        self.cards = []

        self.listbox = tk.Listbox(self, exportselection=False)
        self.listbox.pack(fill="both", expand=True)

        self.filter_input = None

        if filterable:
            filter_frame = tk.Frame(self)
            filter_frame.pack(fill="x", pady=(10, 0))

            tk.Label(
                filter_frame,
                text="Filter by tag:"
            ).pack(anchor="w")

            filter_row = tk.Frame(filter_frame)
            filter_row.pack(fill="x", pady=(3, 0))

            self.filter_input = tk.Entry(filter_row)
            self.filter_input.pack(
                side="left",
                fill="x",
                expand=True
            )

            tk.Button(
                filter_row,
                text="Filter",
                command=self.filter_cards
            ).pack(side="left", padx=(5, 0))

            self.filter_input.bind(
                "<Return>",
                lambda event: self.filter_cards()
            )

    @staticmethod
    def card_label(card):
        return f"{card.id}: {' '.join(card.question.split())}"

    def matching_cards(self):
        if self.filter_input is None:
            return self.all_cards

        target = self.filter_input.get().strip().casefold()

        if not target:
            return self.all_cards

        return [
            card for card in self.all_cards
            if any(
                target in tag.casefold()
                for tag in card.tags
            )
        ]

    def display_cards(self, selected_card_id=None, select_first=False):
        self.cards = self.matching_cards()
        self.listbox.delete(0, "end")

        selected_index = None

        for index, card in enumerate(self.cards):
            self.listbox.insert("end", self.card_label(card))

            if card.id == selected_card_id:
                selected_index = index

        if selected_index is None and select_first and self.cards:
            selected_index = 0

        if selected_index is not None:
            self.listbox.selection_set(selected_index)
            self.listbox.see(selected_index)

    def set_cards(self, cards, selected_card_id=None):
        self.all_cards = list(cards)
        self.display_cards(selected_card_id)

    def filter_cards(self):
        selected_card = self.get_selected_card()
        selected_card_id = selected_card.id if selected_card else None

        self.display_cards(
            selected_card_id=selected_card_id,
            select_first=True
        )
        self.listbox.event_generate("<<ListboxSelect>>")

    def get_selected_card(self):
        selection = self.listbox.curselection()
        return self.cards[selection[0]] if selection else None

    def bind_selection(self, callback):
        self.listbox.bind("<<ListboxSelect>>", callback)

class CardBrowser(tk.Frame):
    def __init__(self, parent, details_title="Selected Card"):
        super().__init__(parent)
        self.selected_card = None
        self.selection_callbacks = []

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=4)

        self.card_panel = CardListPanel(
            self,
            "Select Card",
            filterable=True
        )
        self.card_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 5)
        )

        details_frame = tk.LabelFrame(
            self,
            text=details_title,
            padx=10,
            pady=10
        )
        details_frame.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(5, 0)
        )

        self.card_form = CardForm(
            details_frame,
            editable=False
        )
        self.card_form.pack(fill="both", expand=True)

        self.card_panel.bind_selection(self._selection_changed)

    def refresh_display(self):
        if self.selected_card:
            self.card_form.load_card(self.selected_card)
        else:
            self.card_form.clear()

    def _selection_changed(self, event=None):
        self.selected_card = self.card_panel.get_selected_card()
        self.refresh_display()

        for callback in self.selection_callbacks:
            callback(self.selected_card)

    def set_cards(self, cards, selected_card_id=None):
        self.card_panel.set_cards(cards, selected_card_id)

        if not self.card_panel.get_selected_card() and self.card_panel.cards:
            self.card_panel.listbox.selection_set(0)

        self._selection_changed()

    def get_selected_card(self):
        return self.selected_card

    def bind_selection(self, callback):
        self.selection_callbacks.append(callback)

class ReviewSession:
    def __init__(self, review_items):
        self.review_items = review_items
        self.index = 0

    def current_item(self):
        return self.review_items[self.index]

    def advance(self):
        self.index += 1
        return self.index < len(self.review_items)

def launch_deprecate_card():
    deprecate_window = tk.Toplevel(root)
    deprecate_window.title("Deprecate Cards")
    deprecate_window.geometry("1250x700")

    browser = CardBrowser(
        deprecate_window,
        details_title="Card to Deprecate"
    )
    browser.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=(10, 5)
    )

    def load_cards():
        try:
            browser.set_cards(get_cards_by_tags(["ALL"]))
        except Exception as error:
            messagebox.showerror(
                "Load Failed",
                str(error),
                parent=deprecate_window
            )

    def deprecate_selected_card():
        card = browser.get_selected_card()

        if card is None:
            messagebox.showerror(
                "No card selected",
                "Select a card to deprecate.",
                parent=deprecate_window
            )
            return

        if not messagebox.askyesno(
            "Deprecate Card",
            "Deprecate this card? It will no longer appear in reviews or "
            "active card lists.",
            parent=deprecate_window
        ):
            return

        try:
            deprecate_card(card.id)
            browser.set_cards(get_cards_by_tags(["ALL"]))
        except Exception as error:
            messagebox.showerror(
                "Deprecation Failed",
                str(error),
                parent=deprecate_window
            )
            return

        messagebox.showinfo(
            "Card Deprecated",
            "Card deprecated successfully.",
            parent=deprecate_window
        )

    tk.Button(
        deprecate_window,
        text="Deprecate Card",
        command=deprecate_selected_card
    ).pack(pady=(5, 10))

    load_cards()

def launch_replace_card():
    messagebox.showinfo(
        "Not Implemented",
        "Card replacement will be added later."
    )

def launch_manage_cards():
    manage_window = tk.Toplevel(root)
    manage_window.title("Manage Cards")
    manage_window.geometry("400x350")

    button_frame = tk.Frame(manage_window)
    button_frame.pack(fill="both", expand=True, padx=40, pady=30)

    tk.Button(
        button_frame,
        text="Add Cards",
        command=launch_add_card
    ).pack(fill="x", pady=5)

    tk.Button(
        button_frame,
        text="AI-Assisted Question Creation",
        command=launch_ai_assisted_question_creation
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
    content_frame.grid_columnconfigure(0, weight=5)
    content_frame.grid_columnconfigure(1, weight=2)

    browser = CardBrowser(
        content_frame,
        details_title="Current Card"
    )
    browser.grid(
        row=0,
        column=0,
        sticky="nsew",
        padx=(0, 5)
    )

    new_llm_frame = tk.LabelFrame(
        content_frame,
        text="New LLM Instructions",
        padx=10,
        pady=10
    )
    new_llm_frame.grid(
        row=0,
        column=1,
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

    def display_llm_info(card):
        set_text(
            new_llm_input,
            card.llm_grading_info if card else ""
        )

    def update_llm_info():
        card = browser.get_selected_card()

        if card is None:
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
            update_card_llm_grading_info(card.id, new_info)
        except Exception as error:
            messagebox.showerror(
                "Update Failed",
                str(error),
                parent=update_window
            )
            return

        card.llm_grading_info = new_info
        browser.refresh_display()

        messagebox.showinfo(
            "Card Updated",
            "LLM grading information updated successfully.",
            parent=update_window
        )

    tk.Button(
        new_llm_frame,
        text="Update",
        command=update_llm_info
    ).grid(
        row=1,
        column=0,
        pady=(0, 5)
    )

    browser.bind_selection(display_llm_info)

    try:
        browser.set_cards(get_cards_by_tags(["ALL"]))
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

def launch_add_card():
    add_window = tk.Toplevel(root)
    add_window.title("Add Question")
    add_window.geometry("1100x650")

    card_form = CardForm(add_window)
    card_form.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))

    bottom_frame = tk.Frame(add_window)
    bottom_frame.pack(side="bottom", pady=10)

    def add_handler():
        if insert_question(*card_form.get_values()):
            card_form.clear()

    add_button = tk.Button(bottom_frame, text="Add Question", command=add_handler)
    add_button.pack(side="top")

def launch_ai_assisted_question_creation():
    creation_window = tk.Toplevel(root)
    creation_window.title("AI-Assisted Question Creation")
    creation_window.geometry("1100x750")

    prompt_frame, prompt_input = create_text_panel(
        creation_window,
        "Describe the Question",
        100,
        6
    )
    prompt_frame.pack(fill="x", padx=10, pady=(10, 5))

    draft_form = CardForm(creation_window)
    draft_form.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=5
    )

    controls = tk.Frame(creation_window)
    controls.pack(pady=(5, 10))

    status = tk.StringVar(value="")
    result_queue = Queue()

    def save_draft():
        if insert_question(*draft_form.get_values()):
            draft_form.clear()
            save_button.config(state="disabled")
            status.set("Question saved.")

    def display_draft(result):
        cards = result.get("cards", [])

        if not result.get("card_draft_completed"):
            messagebox.showerror(
                "Question Creation Failed",
                result.get(
                    "error",
                    "The LLM did not return a valid card draft."
                ),
                parent=creation_window
            )
            return

        if not cards:
            messagebox.showerror(
                "Question Creation Failed",
                "The LLM reported success but returned no card draft.",
                parent=creation_window
            )
            return

        draft = cards[0]

        draft_form.load_card(Card(
            question=draft["question"],
            answer=draft["answer"],
            tags=draft["tags"],
            grading_type=draft["grading_type"],
            grading_criteria=draft["grading_criteria"]
        ))


        save_button.config(state="normal")
        status.set(
            f"Draft generated. LLM call ID: {result['llm_call_id']}"
        )

    def poll_for_draft():
        try:
            queue_status, result = result_queue.get_nowait()
        except Empty:
            creation_window.after(100, poll_for_draft)
            return

        generate_button.config(
            text="Generate Draft",
            state="normal"
        )

        if queue_status == "error":
            messagebox.showerror(
                "Question Creation Failed",
                str(result),
                parent=creation_window
            )
            return

        display_draft(result)

    def generate_draft():
        question_input = (
            prompt_input.get("1.0", "end-1c").strip()
        )

        if not question_input:
            messagebox.showerror(
                "Missing Question",
                "Enter the question or question idea to generate.",
                parent=creation_window
            )
            return

        generate_button.config(
            text="Generating...",
            state="disabled"
        )
        status.set("")

        def run_generator():
            try:
                result = generate_card_drafts(
                    question_input,
                    1
                )
                result_queue.put(("success", result))
            except Exception as error:
                result_queue.put(("error", error))

        threading.Thread(
            target=run_generator,
            daemon=True
        ).start()

        creation_window.after(100, poll_for_draft)

    generate_button = tk.Button(
        controls,
        text="Generate Draft",
        command=generate_draft
    )
    generate_button.pack(side="left", padx=5)

    save_button = tk.Button(
        controls,
        text="Save Question",
        command=save_draft,
        state="disabled"
    )
    save_button.pack(side="left", padx=5)

    tk.Label(
        controls,
        textvariable=status
    ).pack(side="left", padx=5)

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
    q_input = tk.Text(q_frame, width=60, height=30, wrap="word", state="disabled")
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
    comparison_input = tk.Text(
        comparison_frame, width=60, height=14, wrap="word", state="disabled"
    )
    comparison_input.pack(fill="both", expand=True, padx=5, pady=5)

    criteria_frame = tk.LabelFrame(grader_frame, text="Grading Criteria")
    criteria_frame.grid(row=1, column=0, sticky="nsew", pady=5)
    criteria_input = tk.Text(
        criteria_frame, width=60, height=5, wrap="word", state="disabled"
    )
    criteria_input.pack(fill="both", expand=True, padx=5, pady=5)

    llm_frame = tk.LabelFrame(grader_frame, text="LLM Grading Info")
    llm_frame.grid(row=2, column=0, sticky="nsew", pady=5)
    llm_input = tk.Text(
        llm_frame, width=60, height=5, wrap="word", state="disabled"
    )
    llm_input.pack(fill="both", expand=True, padx=5, pady=5)

    feedback_frame = tk.LabelFrame(grader_frame, text="AI Feedback")
    feedback_frame.grid(row=3, column=0, sticky="nsew", pady=(5, 0))
    feedback_input = tk.Text(
        feedback_frame, width=60, height=8, wrap="word", state="disabled"
    )
    feedback_input.pack(fill="both", expand=True, padx=5, pady=5)

    bottom_frame = tk.Frame(review_window)
    bottom_frame.pack(side="bottom", pady=10)
    student_controls = tk.Frame(bottom_frame)
    grader_controls = tk.Frame(bottom_frame)

    session = ReviewSession(to_review)
    saved_user_answer = tk.StringVar(value="")
    grade_result = {}
    result_queue = Queue()

    def show_question():
        set_text(q_input, session.current_item().card.question)
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
        card = session.current_item().card
        grade_result.update(result)

        comparison = f"Your Answer:\n{saved_user_answer.get()}\n\nSuggested Answer:\n{card.answer}"
        set_text(comparison_input, comparison)
        set_text(criteria_input, card.grading_criteria or "No grading criteria provided.")
        set_text(llm_input, card.llm_grading_info or "No additional LLM grading information provided.")

        score_text = "Manual grading required" if result["requires_manual_grading"] else f"Score: {result['score']}"
        set_text(feedback_input, f"{score_text}\n\n{result['feedback']}")

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
        review_item = session.current_item()
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
                review_item=session.current_item(),
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

        if not session.advance():
            messagebox.showinfo("Done", "All cards reviewed!")
            review_window.destroy()
            return

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

    tk.Label(q_frame, text="Question").pack(pady=(0, 5))
    q_input = tk.Text(q_frame, width=70, height=30, wrap="word", state="disabled")
    q_input.pack(padx=5, pady=3, fill="both", expand=True)

    a_frame = tk.Frame(qna_frame)
    a_frame.pack(side="left", fill="both", expand=True)

    a_label = tk.Label(a_frame, text="Your Answer")
    a_label.pack(pady=(0, 5))

    a_input = tk.Text(a_frame, width=70, height=30, wrap="word")
    a_input.pack(padx=5, pady=3, fill="both", expand=True)

    bottom_frame = tk.Frame(review_window)
    bottom_frame.pack(side="bottom", pady=10)

    session = ReviewSession(to_review)
    answer_shown = tk.BooleanVar(value=False)
    selected_grade = tk.IntVar(value=0)
    saved_user_answer = tk.StringVar(value="")

    def show_question():
        selected_grade.set(0)
        answer_shown.set(False)
        saved_user_answer.set("")
        set_text(q_input, session.current_item().card.question)
        a_label.config(text="Your Answer")
        a_input.config(state="normal")
        a_input.delete("1.0", "end")
        a_input.focus_set()

        show_ans_btn.config(state="normal")
        submit_grade_btn.config(state="disabled")

        for btn in grade_buttons:
            btn.config(state="disabled")

    def reveal_answer():
        if answer_shown.get():
            return

        review_item = session.current_item()
        user_answer = a_input.get("1.0", "end-1c").strip()
        saved_user_answer.set(user_answer)

        comparison = f"Your Answer:\n{user_answer}\n\nSuggested Answer:\n{review_item.card.answer}\n\nSelect a grade below."
        a_label.config(text="Answer Comparison")
        a_input.config(state="normal")
        set_text(a_input, comparison)
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

        review_item = session.current_item()
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

        if not session.advance():
            messagebox.showinfo("Done", "All cards reviewed!")
            review_window.destroy()
            return

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

    used_panel = CardListPanel(lists_frame, "Cards Used")
    used_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

    separator = tk.Frame(lists_frame, width=2, bg="gray")
    separator.grid(row=0, column=1, sticky="ns")

    available_panel = CardListPanel(lists_frame, "Cards to Add")
    available_panel.grid(row=0, column=2, sticky="nsew", padx=(15, 0))

    def refresh_cards():
        all_cards = get_cards_by_tags(["ALL"])
        used_cards = get_deck_cards(deck)
        used_card_ids = {card.id for card in used_cards}
        cards_to_add = [
            card for card in all_cards
            if card.id not in used_card_ids
        ]
        used_panel.set_cards(used_cards)
        available_panel.set_cards(cards_to_add)

    def add_selected_card():
        card = available_panel.get_selected_card()
        if card is None:
            messagebox.showerror(
                "No card selected",
                "Select a card to add.",
                parent=edit_window
            )
            return

        try:
            add_card_to_deck(deck, card)
            refresh_cards()
        except Exception as error:
            messagebox.showerror("Add failed", str(error), parent=edit_window)

    add_button = tk.Button(
        available_panel,
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
