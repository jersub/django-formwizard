from django import forms
from django.core.urlresolvers import get_callable
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from formwizard.views import wizard

class FormWizard(object):
    """
    The basic FormWizard. This class needs a storage backend when creating
    an instance.
    """

    def __init__(self, storage, form_list, done_view=None, initial_list={}, instance_list={}):
        """
        Creates a form wizard instance. `storage` is the storage backend, the
        place where step data and current state of the form gets saved.

        `form_list` is a list of forms. The list entries can be form classes
        of tuples of (`step_name`, `form_class`).

        `done_view` is the view called to process form data after having gone
        through all steps.

        `initial_list` contains a dictionary of initial data dictionaries.
        The key should be equal to the `step_name` in the `form_list`.

        `instance_list` contains a dictionary of instance objects. This list
        is only used when `ModelForms` are used. The key should be equal to
        the `step_name` in the `form_list`.
        """
        self.form_list = SortedDict()
        self.storage_name = storage

        assert len(form_list) > 0, 'at least one form is needed'

        for i in range(len(form_list)):
            form = form_list[i]
            if isinstance(form, tuple):
                self.form_list[unicode(form[0])] = form[1]
            else:
                self.form_list[unicode(i)] = form

        if done_view:
            self.done = get_callable(done_view)

        self.initial_list = initial_list
        self.instance_list = instance_list

    def __repr__(self):
        return 'step: %s, form_list: %s, initial_list: %s' % (
            self.determine_step(), self.form_list, self.initial_list)

    def __call__(self, request, *args, **kwargs):
        """
        This method gets called by the routing engine. The first argument is
        `request` which contains a `HttpRequest` instance.

        This is a deprecated method to be used in a transitional purpose. The
        routing engine should call the `wizard` view instead.
        """
        return wizard(request, self, {}, *args, **kwargs)

    def render_next_step(self, request, form, *args, **kwargs):
        """
        Gets called when the next step/form should be rendered. `form`
        contains the last/current form.
        """
        next_step = self.get_next_step()
        new_form = self.get_form(next_step, data=self.storage.get_step_data(next_step))
        self.storage.set_current_step(next_step)
        return self.render(request, new_form)

    def render_backward(self, request):
        """
        Gets called when the previous step/form should be rendered.
        """
        self.storage.set_current_step(request.POST['form_prev_step'])
        form = self.get_form(data=self.storage.get_step_data(self.determine_step()))
        return self.render(request, form)

    def render_done(self, request, form, *args, **kwargs):
        """
        Gets called when all forms passed. The method should also re-validate
        all steps to prevent manipulation. If any form don't validate,
        `render_revalidation_failure` should get called. If everything is fine
        call `done`.
        """
        final_form_list = []
        for form_key in self.form_list.keys():
            form_obj = self.get_form(step=form_key, data=self.storage.get_step_data(form_key))
            if not form_obj.is_valid():
                return self.render_revalidation_failure(request, form_key, form_obj)
            final_form_list.append(form_obj)
        return self.done(request, final_form_list)

    def get_form_prefix(self, step=None, form=None):
        """
        Returns the prefix which will be used when calling the actual form for
        the given step. `step` contains the step-name, `form` the form which
        will be called with the returned prefix.

        If no step is given, the form_prefix will determine the current step
        automatically.
        """
        if step is None:
            step = self.determine_step()
        return str(step)

    def get_form_initial(self, step):
        """
        Returns a dictionary which will be passed to the form for `step` 
        as `initial`. If no initial data was provied while initializing the
        form wizard, a empty dictionary will be returned.
        """
        return self.initial_list.get(step, {})

    def get_form_instance(self, step):
        """
        Returns a object which will be passed to the form for `step` 
        as `instance`. If no instance object was provied while initializing
        the form wizard, None be returned.
        """
        return self.instance_list.get(step, None)

    def get_form(self, step=None, data=None):
        """
        Constructs the form for a given `step`. If no `step` is defined, the
        current step will be determined automatically.

        The form will be initialized using the `data` argument to prefill the
        new form.
        """
        if step is None:
            step = self.determine_step()
        kwargs = {
            'data': data,
            'prefix': self.get_form_prefix(step, self.form_list[step]),
            'initial': self.get_form_initial(step),
        }
        if issubclass(self.form_list[step], forms.ModelForm):
            kwargs.update({'instance': self.get_form_instance(step)})
        return self.form_list[step](**kwargs)

    def process_step(self, form):
        """
        This method is used to postprocess the form data. For example, this
        could be used to conditionally skip steps if a special field is
        checked. By default, it returns the raw `form.data` dictionary.
        """
        return self.get_form_step_data(form)

    def render_revalidation_failure(self, request, step, form):
        """
        Gets called when a form doesn't validate before rendering the done
        view. By default, it resets the current step to the first failing
        form and renders the form.
        """
        self.storage.set_current_step(step)
        return self.render(request, form)

    def get_form_step_data(self, form):
        """
        Is used to return the raw form data. You may use this method to
        manipulate the data.
        """
        return form.data

    def get_all_cleaned_data(self):
        """
        Returns a merged dictionary of all step' cleaned_data dictionaries.
        If a step contains a `FormSet`, the key will be prefixed with formset
        and contain a list of the formset' cleaned_data dictionaries.
        """
        cleaned_dict = {}
        for form_key in self.form_list.keys():
            form_obj = self.get_form(step=form_key, data=self.storage.get_step_data(form_key))
            if form_obj.is_valid():
                if isinstance(form_obj.cleaned_data, list):
                    cleaned_dict.update({'formset-%s' % form_key: form_obj.cleaned_data})
                else:
                    cleaned_dict.update(form_obj.cleaned_data)
        return cleaned_dict

    def get_cleaned_data_for_step(self, step):
        """
        Returns the cleaned data for a given `step`. Before returning the
        cleaned data, the stored values are being revalidated through the
        form. If the data doesn't validate, None will be returned.
        """
        if self.form_list.has_key(step):
            form_obj = self.get_form(step=step, data=self.storage.get_step_data(step))
            if form_obj.is_valid():
                return form_obj.cleaned_data
        return None

    def determine_step(self):
        """
        Returns the current step. If no current step is stored in the storage
        backend, the first step will be returned.
        """
        return self.storage.get_current_step() or self.get_first_step()

    def get_first_step(self):
        """
        Returns the name of the first step.
        """
        return self.form_list.keys()[0]

    def get_last_step(self):
        """
        Returns the name of the last step.
        """
        return self.form_list.keys()[-1]

    def get_next_step(self, step=None):
        """
        Returns the next step after the given `step`. If no more steps are
        available, None will be returned. If the `step` argument is None, the
        current step will be determined automatically.
        """
        if step is None:
            step = self.determine_step()
        key = self.form_list.keyOrder.index(step) + 1
        if len(self.form_list.keyOrder) > key:
            return self.form_list.keyOrder[key]
        else:
            return None

    def get_prev_step(self, step=None):
        """
        Returns the previous step before the given `step`. If there are no
        steps available, None will be returned. If the `step` argument is None, the
        current step will be determined automatically.
        """
        if step is None:
            step = self.determine_step()
        key = self.form_list.keyOrder.index(step) - 1
        if key < 0:
            return None
        else:
            return self.form_list.keyOrder[key]

    def get_step_index(self, step=None):
        """
        Returns the index for the given `step` name. If no step is given,
        the current step will be used to get the index.
        """
        if step is None:
            step = self.determine_step()
        return self.form_list.keyOrder.index(step)

    @property
    def num_steps(self):
        """
        Returns the total number of steps/forms in this the wizard.
        """
        return len(self.form_list)

    def get_wizard_name(self):
        """
        Returns the name of the wizard. By default the class name is used.
        This name will be used in storage backends to prevent from colliding
        with other form wizards.
        """
        return self.__class__.__name__

    def reset_wizard(self):
        """
        Resets the user-state of the wizard.
        """
        self.storage.reset()

    def get_template(self):
        """
        Returns the templates to be used for rendering the wizard steps. This
        method can return a list of templates or a single string.
        """
        return 'formwizard/wizard.html'

    def get_extra_context(self):
        """
        Returns the extra data currently stored in the storage backend.
        """
        return self.storage.get_extra_context_data()

    def update_extra_context(self, new_context):
        """
        Updates the currently stored extra context data. Already stored extra
        context will be kept!
        """
        context = self.get_extra_context()
        context.update(new_context)
        return self.storage.set_extra_context_data(context)

    def render(self,request, form):
        """
        Renders the acutal `form`. This method can be used to pre-process data
        or conditionally skip steps.
        """
        return self.render_template(request, form)

    def render_template(self, request, form=None):
        """
        Returns a `HttpResponse` containing the rendered form step. Available
        template context variables are:

         * `extra_context` - current extra context data
         * `form_step` - name of the current step
         * `form_first_step` - name of the first step
         * `form_last_step` - name of the last step
         * `form_prev_step`- name of the previous step
         * `form_next_step` - name of the next step
         * `form_step0` - index of the current step
         * `form_step1` - index of the current step as a 1-index
         * `form_step_count` - total number of steps
         * `form` - form instance of the current step
        """
         
        form = form or self.get_form()
        return render_to_response(self.get_template(), {
            'extra_context': self.get_extra_context(),
            'form_step': self.determine_step(),
            'form_first_step': self.get_first_step(),
            'form_last_step': self.get_last_step(),
            'form_prev_step': self.get_prev_step(),
            'form_next_step': self.get_next_step(),
            'form_step0': int(self.get_step_index()),
            'form_step1': int(self.get_step_index()) + 1,
            'form_step_count': self.num_steps,
            'form': form,
        }, context_instance=RequestContext(request))

    def done(self, request, form_list):
        """
        This method must be overriden by a subclass to process to form data
        after processing all steps.

        This is a deprecated method to be used in a transitional purpose. A
        `done` view should be defined in the routing engine instead.
        """
        raise NotImplementedError("Your %s class has not defined a done() method, which is required." % self.__class__.__name__)

class SessionFormWizard(FormWizard):
    """
    A FormWizard with pre-configured SessionStorageBackend.
    """
    def __init__(self, *args, **kwargs):
        super(SessionFormWizard, self).__init__('formwizard.storage.session.SessionStorage', *args, **kwargs)

class CookieFormWizard(FormWizard):
    """
    A FormWizard with pre-configured CookieStorageBackend.
    """
    def __init__(self, *args, **kwargs):
        super(CookieFormWizard, self).__init__('formwizard.storage.cookie.CookieStorage', *args, **kwargs)
