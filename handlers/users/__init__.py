from . import start
from . import help
from . import access  # grant button, shared contacts, picker cancel; before legacy / AI input
from . import legacy  # old commands / reply-keyboard texts -> hint to the Mini App; before AI input
from . import ai_input  # free text / media -> saved operations or questions; must stay before echo
from . import echo
