import re

def split_text_greedy_by_punctuation(text: str, max_chars: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []

    parts = re.findall(r'.+?[。！？!?；;，,：:\.]+|.+$', text)

    sentences = []
    buf = ""

    def clean_tail_punctuation(s: str) -> str:
        return s.rstrip("，,")

    def hard_split(s: str):
        return [
            clean_tail_punctuation(s[i:i + max_chars])
            for i in range(0, len(s), max_chars)
        ]

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if len(part) > max_chars:
            if buf:
                sentences.append(clean_tail_punctuation(buf))
                buf = ""

            sentences.extend(hard_split(part))
            continue

        if len(buf) + len(part) <= max_chars:
            buf += part
        else:
            if buf:
                sentences.append(clean_tail_punctuation(buf))
            buf = part

    if buf:
        sentences.append(clean_tail_punctuation(buf))

    return sentences

if __name__ == "__main__":
    
    text = """大家好，Good morning everyone! 今天我想和大家分享一个主题——拥抱变化，持续成长（Embrace Change, Keep Growing）。在这个快速发展的时代，technology is changing everything around us. 从人工智能到智能设备，从在线教育到远程办公，我们每天都在面对新的挑战和新的机会。很多时候，变化会让人感到不安，因为它意味着我们需要离开舒适区（comfort zone）。但是，正是这些变化，推动着我们不断进步。There is a famous saying: "Life begins at the end of your comfort zone." 当我们勇敢尝试新的事物时，才能发现自己真正的潜力。也许第一次公开演讲会紧张，第一次学习编程会遇到困难，第一次承担重要项目会感到压力巨大，但是 every expert was once a beginner. 每一位专家，都曾经是一个不断学习的新手。对于我们来说，持续学习（continuous learning）已经不再是一种选择，而是一种必需。The world will not stop moving forward because we stop learning. 无论你是一名学生、一位工程师、一名教师，还是一位管理者，learning new skills will always create new opportunities. 当我们保持好奇心，保持开放的心态，我们就能够在变化中发现机遇，在挑战中实现成长。同时，我们也要学会正确看待失败。Failure is not the opposite of success; it is part of success. 每一次失败都在帮助我们积累经验，每一次挫折都在帮助我们变得更加强大。特别是在人工智能时代，AI is becoming a powerful partner rather than a competitor. 它能够帮助我们提高效率、获取知识、激发创造力，但真正决定未来的，仍然是人的思考能力、创新能力以及解决问题的能力。最后，我想用一句话与大家共勉：The future belongs to those who are willing to learn, adapt, and grow. 未来属于那些愿意学习、愿意适应变化、愿意不断成长的人。让我们一起 stay curious, stay passionate, and keep growing. 勇敢迎接每一个新的挑战，创造属于自己的精彩未来。Thank you for your attention, and wish you all a bright and successful future! 谢谢大家！"""
    
    
    sentences = split_text_greedy_by_punctuation(text)
    print(sentences)