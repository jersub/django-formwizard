from django.core.urlresolvers import get_callable
from formwizard.storage import get_storage

def wizard(request, wizard, step_views={}):
    """TODO doc"""
    _init_wizard_view(request, wizard)

    if not 'default' in step_views:
        step_views['default'] = 'formwizard.views.wizard_default_step'

    response = _process_request(request, wizard, step_views)
    response = wizard.storage.update_response(response)

    return response

def wizard_default_step(request, wizard):
    """TODO doc"""
    form = wizard.get_form(data=request.POST)

    if form.is_valid():
        wizard.storage.set_step_data(wizard.determine_step(), wizard.process_step(form))

        if wizard.determine_step() == wizard.get_last_step():
            return wizard.render_done(form)
        else:
            return wizard.render_next_step(wizard, form)

    return wizard.render(form)

def _process_request(request, wizard, step_views):
    """TODO doc"""
    if request.method == 'GET':
        return wizard.process_reset()

    else:
        if request.POST.has_key('form_prev_step') and wizard.form_list.has_key(request.POST['form_prev_step']):
            return wizard.render_backward(request)

        current_step = wizard.storage.get_current_step()

        if current_step in step_views:
            step_view = get_callable(step_views[current_step])
        else:
            step_view = get_callable(step_views['default'])

        return step_view(request, wizard)

def _init_wizard_view(request, wizard):
    """TODO doc"""
    wizard.request = request
    wizard.storage = get_storage(wizard.storage_name, wizard.get_wizard_name(), wizard.request)
