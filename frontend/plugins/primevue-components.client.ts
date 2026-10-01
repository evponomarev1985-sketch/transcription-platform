import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Card from 'primevue/card'
import Toast from 'primevue/toast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import FileUpload from 'primevue/fileupload'
import Sidebar from 'primevue/sidebar'
import Dialog from 'primevue/dialog'
import ConfirmDialog from 'primevue/confirmdialog'
import Skeleton from 'primevue/skeleton'
import Textarea from 'primevue/textarea'
import Dropdown from 'primevue/dropdown'
import MultiSelect from 'primevue/multiselect'
import InputNumber from 'primevue/inputnumber'
import InputSwitch from 'primevue/inputswitch'

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.component('PButton', Button)
  nuxtApp.vueApp.component('PInputText', InputText)
  nuxtApp.vueApp.component('PPassword', Password)
  nuxtApp.vueApp.component('PCard', Card)
  nuxtApp.vueApp.component('PToast', Toast)
  nuxtApp.vueApp.component('PDataTable', DataTable)
  nuxtApp.vueApp.component('PColumn', Column)
  nuxtApp.vueApp.component('PTag', Tag)
  nuxtApp.vueApp.component('PProgressBar', ProgressBar)
  nuxtApp.vueApp.component('PFileUpload', FileUpload)
  nuxtApp.vueApp.component('PSidebar', Sidebar)
  nuxtApp.vueApp.component('PDialog', Dialog)
  nuxtApp.vueApp.component('PConfirmDialog', ConfirmDialog)
  nuxtApp.vueApp.component('PSkeleton', Skeleton)
  nuxtApp.vueApp.component('PTextarea', Textarea)
  nuxtApp.vueApp.component('PDropdown', Dropdown)
  nuxtApp.vueApp.component('PMultiSelect', MultiSelect)
  nuxtApp.vueApp.component('PInputNumber', InputNumber)
  nuxtApp.vueApp.component('PInputSwitch', InputSwitch)
})
