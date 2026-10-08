"""Skill names: the same skill is written in many ways ("Postgres", "PostgreSQL"; "JS", "JavaScript").

    skill_key(name)                          one simple form of a skill name, to compare two names
    find_skill(skill, cv_skills, cv_text)    where the CV shows the skill, or "" if it does not

The list below is short on purpose. Add a line when a real CV uses another name for a skill.
"""
import re

# other name -> one name
OTHER_NAMES = {
    "js": "javascript", "ecmascript": "javascript",
    "ts": "typescript",
    "postgres": "postgresql", "psql": "postgresql",
    "nodejs": "node.js", "node": "node.js",
    "reactjs": "react", "react.js": "react",
    "vuejs": "vue", "vue.js": "vue",
    "nextjs": "next.js",
    "golang": "go",
    "k8s": "kubernetes",
    "c sharp": "c#", "csharp": "c#",
    "dotnet": ".net", ".net core": ".net", "asp.net": ".net",
    "mongo": "mongodb",
    "amazon web services": "aws",
    "google cloud": "gcp", "google cloud platform": "gcp",
    "ml": "machine learning",
    "rest": "rest api", "restful api": "rest api", "rest apis": "rest api", "restful apis": "rest api",
    "py": "python", "python3": "python",
}


def skill_key(name: str) -> str:
    key = re.sub(r"\s+", " ", str(name).lower().strip())
    return OTHER_NAMES.get(key, key)


def find_skill(skill: str, cv_skills: list[str], cv_text: str) -> str:
    """How the CV shows the skill, in plain words, or "" if it does not.
    "Python or JavaScript" (also "Python / JavaScript") is met when the CV shows either of them."""
    choices = [part for part in re.split(r"\s+or\s+|\s+/\s+", str(skill).strip(), flags=re.IGNORECASE) if part.strip()]
    if len(choices) > 1:
        for choice in choices:
            how = find_skill(choice, cv_skills, cv_text)
            if how:
                return how
        return ""
    key = skill_key(skill)
    if key in {skill_key(s) for s in cv_skills}:
        return "listed in the CV's skills"
    if len(key) <= 2:                             # "go", "r", "c": too short to look for in free text
        return ""
    names = {key, str(skill).lower().strip()} | {other for other, one in OTHER_NAMES.items() if one == key and len(other) > 2}
    text = cv_text.lower()
    for name in sorted(names):
        if re.search(rf"(?<![\w.+#]){re.escape(name)}(?![\w+#])", text):
            return f"the CV mentions \"{name}\""
    return ""
