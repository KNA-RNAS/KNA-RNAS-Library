# Configuration file for the Sphinx documentation builder.

# -- Project information

project = 'KNA-RNAS Library'
copyright = '2025-present Koninklijke Nederlandse Astronomenclub'
author = 'Noel-Storr, and secretaries'

release = '0.1'
version = '0.1.0'

# -- General configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx_design',
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

# -- Internationalization ----------------------------------------------------

language = 'en'
locale_dirs = ['../locale/']   # path is relative to source/
gettext_compact = False

templates_path = ['_templates']

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'

html_theme_options = {
    'logo_only': True,
    'display_version': False,
    'style_nav_header_background': '#1a2a6b', # Society Dark Blue
}

html_logo = "_static/logo_white.png"

# -- Options for EPUB output
epub_show_urls = 'footnote'

extensions.append("sphinx.ext.todo")
todo_include_todos = True

# -- Custom style file
html_static_path = ["_static"]

html_css_files = [
    "style.css",
]

# -- Custom Extensions -----------------------------------------------------

from docutils import nodes
from docutils.parsers.rst import Directive, directives

class DocumentOfRecordDirective(Directive):
    """Directive to display a banner indicating the document of record."""
    has_content = True
    option_spec = {
        'original-lang': directives.unchanged,
    }
    
    def run(self):
        env = self.state.document.settings.env
        lang = getattr(env.config, 'language', 'en')
        original_lang = self.options.get('original-lang', 'en')
        
        is_translation = lang != original_lang
        
        # Message based on language and translation status
        if lang == 'nl':
            if is_translation:
                msg = "Dit is een vertaling. Het originele document is in het Engels."
            else:
                msg = "Dit is het officiële document van record (Origineel)."
        else:
            if is_translation:
                msg = "This is a translation. The original document is in Dutch."
            else:
                msg = "This is the official document of record (Original)."
            
        banner_node = nodes.container()
        banner_node['classes'].append('document-of-record-banner')
        if is_translation:
            banner_node['classes'].append('translation-banner')
        
        # Icon and Text
        icon_class = "fa-language" if is_translation else "fa-certificate"
        icon_html = nodes.raw('', f'<i class="fa {icon_class}"></i> ', format='html')
        text_node = nodes.Text(msg)
        
        banner_node.append(icon_html)
        banner_node.append(text_node)
        
        return [banner_node]

class DocumentStatusDirective(Directive):
    """Directive to display document approval and notary status."""
    has_content = False
    option_spec = {
        'approved': directives.unchanged,
        'approved_in': directives.unchanged,
        'notary_stamp': directives.unchanged,
    }

    def run(self):
        approved = self.options.get('approved', None)
        approved_in = self.options.get('approved_in', None)
        notary_stamp = self.options.get('notary_stamp', None)

        container = nodes.container(classes=['document-status-box'])

        if approved is not None:
            is_approved = approved.lower() in ('true', 'yes', 'y', '1')
            p = nodes.paragraph(classes=['status-approval'])
            
            if is_approved:
                icon_html = nodes.raw('', '<i class="fa fa-check-circle" style="color: green;"></i> ', format='html')
                text = "Official & Approved"
                p.append(icon_html)
                p.append(nodes.strong(text, text))
                
                if approved_in:
                    p.append(nodes.Text(" - Approved in: "))
                    inliner, messages = self.state.inline_text(approved_in, self.lineno)
                    p.extend(inliner)
            else:
                icon_html = nodes.raw('', '<i class="fa fa-exclamation-triangle" style="color: #d4a96a;"></i> ', format='html')
                text = "Draft / Unapproved"
                p.append(icon_html)
                p.append(nodes.strong(text, text))
            
            container.append(p)

        if notary_stamp is not None and notary_stamp.lower() != 'pending':
            p = nodes.paragraph(classes=['status-notary'])
            icon_html = nodes.raw('', '<i class="fa fa-institution" style="color: #1a2a6b;"></i> ', format='html')
            text = f"Notary Stamped: {notary_stamp}"
            
            p.append(icon_html)
            p.append(nodes.strong(text, text))
            container.append(p)

        return [container]

def setup(app):
    app.add_directive("document-of-record", DocumentOfRecordDirective)
    app.add_directive("document-status", DocumentStatusDirective)